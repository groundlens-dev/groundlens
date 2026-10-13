# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Where records are kept.

A sink keeps one chain of records: each record names the hash of the one
before it. :meth:`groundlens.Verifier.check` stores the record in the sink
before it returns the decision; if the record cannot be stored, ``check``
raises and no decision comes back.

- :func:`jsonl`: a JSON Lines file on disk, flushed to disk on every write.
- :func:`s3_object_lock`: one object per record in an S3 bucket with Object
  Lock, written only if absent, optionally with a retention date.
- :func:`azure_blob`: one blob per record in a container with an
  immutability policy, written only if absent.
- :func:`postgres`: one row per record, with the chain position as part of
  the primary key.

Many processes can write at once: give each one its own chain
(``chain="worker-3"``), and verify them together with
``groundlens record verify``. Two writers on the same chain are detected:
the second write of the same position fails, and ``check`` re-reads the head
and seals again.

You pass the client you already use (``boto3``, ``azure-storage-blob``, a
DB-API connection such as ``psycopg``). GroundLens depends on none of them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from groundlens.record import Record


class StoreError(RuntimeError):
    """The record could not be stored. No decision is returned without it."""


class ChainConflict(StoreError):
    """Another writer extended this chain first. Seal again on the new head."""


@runtime_checkable
class Sink(Protocol):
    """A chain of records.

    ``head`` is the ``record_hash`` of the last record, or ``None`` for an
    empty chain. ``append`` stores a record whose ``previous_record_hash`` is
    the current head and raises :class:`ChainConflict` if it is not, or
    :class:`StoreError` if it cannot store it. ``records`` reads the chain back
    in order.
    """

    def head(self) -> str | None: ...

    def append(self, record: Record) -> None: ...

    def records(self) -> list[Record]: ...


def _check_link(record: Record, head: str | None) -> None:
    if record.previous_record_hash != head:
        raise ChainConflict(
            f"record {record.record_id} follows {record.previous_record_hash}, but the chain ends at {head}"
        )


# ---- JSON Lines ------------------------------------------------------------------


class JsonlSink:
    """A JSON Lines file. Every append is flushed and fsynced before it returns."""

    def __init__(self, path: str | Path, chain: str = "records") -> None:
        p = Path(path)
        if p.suffix != ".jsonl":
            p = p / f"{chain}.jsonl"
        self.path = p
        self.chain = chain

    def head(self) -> str | None:
        line = _last_line(self.path)
        return json.loads(line)["record_hash"] if line else None

    def append(self, record: Record) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("a+", encoding="utf-8") as f:
                _lock(f)
                try:
                    _check_link(record, self.head())
                    f.write(record.to_json() + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    _unlock(f)
        except ChainConflict:
            raise
        except OSError as e:
            raise StoreError(f"{self.path}: {e}") from e

    def records(self) -> list[Record]:
        return Record.read_log(self.path) if self.path.exists() else []


def jsonl(path: str | Path, chain: str = "records") -> JsonlSink:
    """Keep records in a JSON Lines file. A path ending in ``.jsonl`` is the
    file; any other path is a directory, and the file is ``<chain>.jsonl`` in it."""
    return JsonlSink(path, chain)


def _last_line(path: Path) -> str | None:
    if not path.exists():
        return None
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        block = b""
        pos = end
        while pos > 0:
            step = min(4096, pos)
            pos -= step
            f.seek(pos)
            block = f.read(step) + block
            lines = [ln for ln in block.split(b"\n") if ln.strip()]
            if len(lines) > 1 or (lines and pos == 0):
                return lines[-1].decode("utf-8")
        return None


def _lock(f: Any) -> None:
    try:
        import fcntl  # noqa: PLC0415 - POSIX only
    except ImportError:  # pragma: no cover - Windows: one writer per chain
        return
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)


def _unlock(f: Any) -> None:
    try:
        import fcntl  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        return
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# ---- Object stores ---------------------------------------------------------------


def _position_key(prefix: str, chain: str, position: int) -> str:
    return f"{prefix.rstrip('/')}/{chain}/{position:012d}.json"


class S3ObjectLockSink:
    """One object per record, ``<prefix>/<chain>/<position>.json``.

    The bucket must have Object Lock enabled. Each object is written with
    ``If-None-Match: *``, so a position is written once; with
    ``retain_days`` it also gets a retention date in ``mode`` (``COMPLIANCE``
    by default: not even the account root can delete it before then).
    """

    def __init__(
        self,
        client: Any,
        bucket: str,
        prefix: str = "groundlens",
        chain: str = "records",
        retain_days: int | None = None,
        mode: str = "COMPLIANCE",
    ) -> None:
        self.client = client
        self.bucket = bucket
        self.prefix = prefix
        self.chain = chain
        self.retain_days = retain_days
        self.mode = mode

    def _keys(self) -> list[str]:
        keys: list[str] = []
        token = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": f"{self.prefix.rstrip('/')}/{self.chain}/"}
            if token:
                kwargs["ContinuationToken"] = token
            page = self.client.list_objects_v2(**kwargs)
            keys.extend(o["Key"] for o in page.get("Contents", []))
            if not page.get("IsTruncated"):
                return sorted(keys)
            token = page.get("NextContinuationToken")

    def _read(self, key: str) -> Record:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return Record.from_json(body.decode("utf-8") if isinstance(body, bytes) else body)

    def head(self) -> str | None:
        keys = self._keys()
        return self._read(keys[-1]).record_hash if keys else None

    def append(self, record: Record) -> None:
        import datetime as dt  # noqa: PLC0415

        keys = self._keys()
        head = self._read(keys[-1]).record_hash if keys else None
        _check_link(record, head)
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": _position_key(self.prefix, self.chain, len(keys)),
            "Body": record.to_json().encode("utf-8"),
            "ContentType": "application/json",
            "IfNoneMatch": "*",
            "ChecksumAlgorithm": "SHA256",
        }
        if self.retain_days is not None:
            kwargs["ObjectLockMode"] = self.mode
            kwargs["ObjectLockRetainUntilDate"] = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=self.retain_days)
        try:
            self.client.put_object(**kwargs)
        except Exception as e:  # noqa: BLE001 - botocore errors are not importable here
            code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if code in ("PreconditionFailed", "ConditionalRequestConflict"):
                raise ChainConflict(f"position {len(keys)} of chain {self.chain} was written by another writer") from e
            raise StoreError(f"s3://{self.bucket}/{kwargs['Key']}: {e}") from e

    def records(self) -> list[Record]:
        return [self._read(k) for k in self._keys()]


def s3_object_lock(
    client: Any,
    bucket: str,
    prefix: str = "groundlens",
    chain: str = "records",
    retain_days: int | None = None,
    mode: str = "COMPLIANCE",
) -> S3ObjectLockSink:
    """Keep records in S3 with Object Lock. ``client`` is ``boto3.client("s3")``."""
    return S3ObjectLockSink(client, bucket, prefix, chain, retain_days, mode)


class AzureBlobSink:
    """One blob per record, ``<prefix>/<chain>/<position>.json``.

    Give the container (or the storage account) a time-based immutability
    policy so a written blob cannot be changed or deleted. Each blob is written
    with ``overwrite=False``, so a position is written once.
    """

    def __init__(self, container_client: Any, prefix: str = "groundlens", chain: str = "records") -> None:
        self.container = container_client
        self.prefix = prefix
        self.chain = chain

    def _names(self) -> list[str]:
        start = f"{self.prefix.rstrip('/')}/{self.chain}/"
        return sorted(b.name for b in self.container.list_blobs(name_starts_with=start))

    def _read(self, name: str) -> Record:
        data = self.container.download_blob(name).readall()
        return Record.from_json(data.decode("utf-8") if isinstance(data, bytes) else data)

    def head(self) -> str | None:
        names = self._names()
        return self._read(names[-1]).record_hash if names else None

    def append(self, record: Record) -> None:
        names = self._names()
        head = self._read(names[-1]).record_hash if names else None
        _check_link(record, head)
        name = _position_key(self.prefix, self.chain, len(names))
        try:
            self.container.upload_blob(name, record.to_json().encode("utf-8"), overwrite=False)
        except Exception as e:  # noqa: BLE001 - azure errors are not importable here
            if type(e).__name__ == "ResourceExistsError":
                raise ChainConflict(f"{name} was written by another writer") from e
            raise StoreError(f"{name}: {e}") from e

    def records(self) -> list[Record]:
        return [self._read(n) for n in self._names()]


def azure_blob(container_client: Any, prefix: str = "groundlens", chain: str = "records") -> AzureBlobSink:
    """Keep records in Azure Blob storage. ``container_client`` is an
    ``azure.storage.blob.ContainerClient`` for a container with an
    immutability policy."""
    return AzureBlobSink(container_client, prefix, chain)


# ---- Postgres --------------------------------------------------------------------


class PostgresSink:
    """One row per record. ``(chain, position)`` is the primary key, so a
    position is written once, and ``previous_record_hash`` is unique per
    chain, so a chain cannot fork."""

    def __init__(self, connection: Any, table: str = "groundlens_records", chain: str = "records", paramstyle: str = "format") -> None:
        if not table.replace("_", "").isalnum():
            raise ValueError("table must be a plain identifier")
        self.conn = connection
        self.table = table
        self.chain = chain
        self.p = "%s" if paramstyle == "format" else "?"
        cur = self.conn.cursor()
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS {table} ("  # noqa: S608 - identifier checked above
            "chain TEXT NOT NULL, position BIGINT NOT NULL, record_id TEXT NOT NULL, "
            "record_hash TEXT NOT NULL, previous_record_hash TEXT, record TEXT NOT NULL, "
            "PRIMARY KEY (chain, position), UNIQUE (chain, previous_record_hash))"
        )
        self.conn.commit()

    def _last(self) -> tuple[int, str] | None:
        cur = self.conn.cursor()
        cur.execute(
            f"SELECT position, record_hash FROM {self.table} WHERE chain = {self.p} ORDER BY position DESC LIMIT 1",  # noqa: S608
            (self.chain,),
        )
        row = cur.fetchone()
        return (int(row[0]), str(row[1])) if row else None

    def head(self) -> str | None:
        last = self._last()
        return last[1] if last else None

    def append(self, record: Record) -> None:
        last = self._last()
        _check_link(record, last[1] if last else None)
        position = last[0] + 1 if last else 0
        try:
            cur = self.conn.cursor()
            cur.execute(
                f"INSERT INTO {self.table} (chain, position, record_id, record_hash, previous_record_hash, record) "  # noqa: S608
                f"VALUES ({', '.join([self.p] * 6)})",
                (self.chain, position, record.record_id, record.record_hash, record.previous_record_hash, record.to_json()),
            )
            self.conn.commit()
        except Exception as e:  # noqa: BLE001 - each driver has its own error classes
            self.conn.rollback()
            if "unique" in str(e).lower() or "duplicate" in str(e).lower() or type(e).__name__ == "IntegrityError":
                raise ChainConflict(f"position {position} of chain {self.chain} was written by another writer") from e
            raise StoreError(f"{self.table}: {e}") from e

    def records(self) -> list[Record]:
        cur = self.conn.cursor()
        cur.execute(f"SELECT record FROM {self.table} WHERE chain = {self.p} ORDER BY position", (self.chain,))  # noqa: S608
        return [Record.from_json(row[0]) for row in cur.fetchall()]


def postgres(connection: Any, table: str = "groundlens_records", chain: str = "records", paramstyle: str = "format") -> PostgresSink:
    """Keep records in Postgres. ``connection`` is a DB-API connection
    (``psycopg.connect(...)``). The table is created if it does not exist.
    ``paramstyle="qmark"`` makes it usable with ``sqlite3`` for tests."""
    return PostgresSink(connection, table, chain, paramstyle)
