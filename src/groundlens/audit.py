"""Hash-chain immutable audit log for regulated deployments.

This module provides a persistent, cryptographically linked log of
groundlens evaluations. Each entry's hash is computed over (a) the
entry payload, (b) the hash of the previous entry, and (c) the entry
timestamp. Any post-hoc modification breaks the chain and is detectable
via :meth:`AuditLog.verify_chain`.

The implementation deliberately uses only SHA-256 (FIPS 180-4) and
standard-library SQLite. No third-party crypto dependencies, no
optional installs. The hash chain pattern is the same as used in
certificate transparency (RFC 6962) and supervised banking model risk
tooling: every later entry's validity depends on the integrity of all
earlier entries.

Typical usage::

    from groundlens.audit import AuditLog

    log = AuditLog(db_path="audit.sqlite")

    entry = log.record(
        identifier="case_2026_06_08_001",
        method="sgi",
        score=1.23,
        flagged=False,
        inputs={"question": "...", "response": "...", "context": "..."},
        metadata={"operator": "compliance_officer_42"},
    )

    # Later, for an examiner:
    is_valid, broken_at = log.verify_chain()
    assert is_valid

    # Export for an examiner
    log.export_jsonl("audit_2026_06_export.jsonl")

The log is single-writer single-process. Concurrent writes from
multiple processes against the same SQLite file are not supported by
design — split into per-process logs and reconcile downstream if
multi-process logging is required.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

# ── Constants ───────────────────────────────────────────────────────────────


_GENESIS_HASH: str = "0" * 64
"""The canonical predecessor hash for the first chain entry."""


_SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS audit_entries (
    entry_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    identifier    TEXT NOT NULL,
    method        TEXT NOT NULL,
    score         REAL,
    flagged       INTEGER NOT NULL,
    payload_json  TEXT NOT NULL,
    prev_hash     TEXT NOT NULL,
    entry_hash    TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_entries(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_audit_identifier ON audit_entries(identifier);
CREATE INDEX IF NOT EXISTS idx_audit_method ON audit_entries(method);
CREATE INDEX IF NOT EXISTS idx_audit_flagged ON audit_entries(flagged);
"""


# ── Types ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """A single record in the audit log.

    Attributes:
        entry_id: Auto-incremented row id.
        timestamp_utc: ISO-8601 UTC timestamp recorded at write time.
        identifier: Caller-supplied identifier (e.g. case_id, request_id).
        method: Scoring method (``"sgi"``, ``"dgi"``, ``"rules"``, ``"hybrid"``).
        score: The numeric score (may be ``None`` for rule-only entries).
        flagged: Whether the evaluation was flagged for review.
        payload_json: JSON-encoded full payload (inputs + metadata + score).
        prev_hash: SHA-256 hex digest of the previous entry's ``entry_hash``,
            or the genesis hash for the first entry.
        entry_hash: SHA-256 hex digest of (prev_hash + payload_json + timestamp).
    """

    entry_id: int
    timestamp_utc: str
    identifier: str
    method: str
    score: float | None
    flagged: bool
    payload_json: str
    prev_hash: str
    entry_hash: str


@dataclass(frozen=True, slots=True)
class ChainVerification:
    """Result of a chain-integrity verification.

    Attributes:
        valid: Whether the full chain hashes correctly.
        broken_at_entry_id: ``None`` if valid; otherwise the entry_id at
            which the chain breaks (the first entry whose recomputed hash
            does not match the stored ``entry_hash``).
        entries_checked: How many entries were verified.
        reason: Short human-readable explanation if broken.
    """

    valid: bool
    broken_at_entry_id: int | None
    entries_checked: int
    reason: str = ""


# ── Hash helper ─────────────────────────────────────────────────────────────


def _compute_entry_hash(prev_hash: str, payload_json: str, timestamp_utc: str) -> str:
    """Compute SHA-256 of (prev_hash + payload_json + timestamp) as hex."""
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(payload_json.encode("utf-8"))
    h.update(timestamp_utc.encode("utf-8"))
    return h.hexdigest()


def _canonical_json(payload: dict[str, Any]) -> str:
    """Serialize a payload deterministically for hash stability.

    Uses sorted keys and no extra whitespace. Two equal Python dicts
    always produce the same JSON string, which is required for the
    chain hash to be reproducible.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ── AuditLog ────────────────────────────────────────────────────────────────


class AuditLog:
    """Append-only hash-chain audit log backed by SQLite.

    Use as a long-lived object whose connection stays open for the
    lifetime of the process. Closes automatically on ``__del__`` or
    explicitly via :meth:`close`.

    Args:
        db_path: Path to the SQLite database file. ``None`` or ``":memory:"``
            uses an in-memory database (useful for testing; not durable).

    Example:
        >>> log = AuditLog(db_path="audit.sqlite")
        >>> entry = log.record(
        ...     identifier="req_001",
        ...     method="sgi",
        ...     score=1.23,
        ...     flagged=False,
        ...     inputs={"question": "Q", "response": "A", "context": "C"},
        ... )
        >>> log.verify_chain().valid
        True
    """

    def __init__(self, *, db_path: str | Path | None = None) -> None:
        if db_path is None or db_path == ":memory:":
            self._db_path: str = ":memory:"
        else:
            self._db_path = str(Path(db_path))
        self._conn: sqlite3.Connection = sqlite3.connect(
            self._db_path,
            isolation_level=None,  # autocommit
            check_same_thread=True,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)

    # ── Recording ───────────────────────────────────────────────────────────

    def record(
        self,
        *,
        identifier: str,
        method: str,
        flagged: bool,
        score: float | None = None,
        inputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        rule_results: list[dict[str, Any]] | None = None,
        compliance_mapping: dict[str, Any] | None = None,
        timestamp_utc: str | None = None,
    ) -> AuditEntry:
        """Append a new entry to the hash chain.

        Args:
            identifier: A caller-supplied opaque identifier (case_id,
                request_id, etc.). Indexed for examiner queries.
            method: The scoring method used.
            flagged: Whether the evaluation was flagged.
            score: Numeric score (raw or normalized — convention chosen
                by the deployment). May be ``None``.
            inputs: The inputs to the scorer (question, response,
                context). Stored verbatim in the payload.
            metadata: Arbitrary additional metadata (operator id, batch
                id, environment, etc.).
            rule_results: Optional list of rule-level results, e.g.
                from :meth:`groundlens.rules.RuleSet.evaluate`.
            compliance_mapping: Optional structured mapping snapshot.
            timestamp_utc: Override timestamp (used only for testing
                reproducibility). Defaults to current UTC time.

        Returns:
            The :class:`AuditEntry` that was written.
        """
        ts = timestamp_utc or _dt.datetime.now(_dt.timezone.utc).isoformat()

        payload: dict[str, Any] = {
            "identifier": identifier,
            "method": method,
            "score": score,
            "flagged": bool(flagged),
            "inputs": inputs or {},
            "metadata": metadata or {},
            "rule_results": rule_results or [],
            "compliance_mapping": compliance_mapping or {},
        }
        payload_json = _canonical_json(payload)

        prev_hash = self._latest_hash()
        entry_hash = _compute_entry_hash(prev_hash, payload_json, ts)

        cursor = self._conn.execute(
            """
            INSERT INTO audit_entries
              (timestamp_utc, identifier, method, score, flagged,
               payload_json, prev_hash, entry_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, identifier, method, score, int(bool(flagged)),
             payload_json, prev_hash, entry_hash),
        )
        entry_id = cursor.lastrowid
        assert entry_id is not None

        return AuditEntry(
            entry_id=entry_id,
            timestamp_utc=ts,
            identifier=identifier,
            method=method,
            score=score,
            flagged=bool(flagged),
            payload_json=payload_json,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )

    def _latest_hash(self) -> str:
        """Return the latest entry's hash, or the genesis hash if empty."""
        row = self._conn.execute(
            "SELECT entry_hash FROM audit_entries ORDER BY entry_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return _GENESIS_HASH
        return str(row["entry_hash"])

    # ── Reading ─────────────────────────────────────────────────────────────

    def count(self) -> int:
        """Return the number of entries in the log."""
        row = self._conn.execute("SELECT COUNT(*) AS n FROM audit_entries").fetchone()
        return int(row["n"])

    def entries(self, *, limit: int | None = None) -> Iterator[AuditEntry]:
        """Iterate entries in insertion order.

        Args:
            limit: If given, yield at most this many entries.

        Yields:
            :class:`AuditEntry` instances.
        """
        sql = "SELECT * FROM audit_entries ORDER BY entry_id ASC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        for row in self._conn.execute(sql):
            yield _row_to_entry(row)

    def get(self, entry_id: int) -> AuditEntry | None:
        """Return a specific entry by id, or ``None`` if not found."""
        row = self._conn.execute(
            "SELECT * FROM audit_entries WHERE entry_id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    def find_flagged(self, *, limit: int | None = None) -> Iterator[AuditEntry]:
        """Iterate flagged entries in insertion order."""
        sql = "SELECT * FROM audit_entries WHERE flagged = 1 ORDER BY entry_id ASC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        for row in self._conn.execute(sql):
            yield _row_to_entry(row)

    # ── Verification ────────────────────────────────────────────────────────

    def verify_chain(self) -> ChainVerification:
        """Replay the chain from the genesis and verify every hash.

        Returns:
            A :class:`ChainVerification` describing the result. If
            ``valid`` is ``False``, ``broken_at_entry_id`` indicates the
            first entry whose stored hash does not match the recomputed
            value (i.e. evidence of tampering or corruption).
        """
        expected_prev = _GENESIS_HASH
        checked = 0
        for entry in self.entries():
            recomputed = _compute_entry_hash(
                entry.prev_hash, entry.payload_json, entry.timestamp_utc
            )
            if entry.prev_hash != expected_prev:
                return ChainVerification(
                    valid=False,
                    broken_at_entry_id=entry.entry_id,
                    entries_checked=checked,
                    reason=f"prev_hash mismatch at entry {entry.entry_id}",
                )
            if recomputed != entry.entry_hash:
                return ChainVerification(
                    valid=False,
                    broken_at_entry_id=entry.entry_id,
                    entries_checked=checked,
                    reason=f"entry_hash mismatch at entry {entry.entry_id}",
                )
            expected_prev = entry.entry_hash
            checked += 1

        return ChainVerification(
            valid=True,
            broken_at_entry_id=None,
            entries_checked=checked,
        )

    # ── Export ──────────────────────────────────────────────────────────────

    def export_jsonl(self, path: str | Path) -> int:
        """Export all entries to a JSON Lines file. Returns count written."""
        n = 0
        target = Path(path)
        with target.open("w", encoding="utf-8") as f:
            for entry in self.entries():
                f.write(
                    json.dumps(
                        {
                            "entry_id": entry.entry_id,
                            "timestamp_utc": entry.timestamp_utc,
                            "identifier": entry.identifier,
                            "method": entry.method,
                            "score": entry.score,
                            "flagged": entry.flagged,
                            "payload": json.loads(entry.payload_json),
                            "prev_hash": entry.prev_hash,
                            "entry_hash": entry.entry_hash,
                        },
                        ensure_ascii=False,
                    )
                )
                f.write("\n")
                n += 1
        return n

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with contextlib.suppress(sqlite3.Error):
            self._conn.close()

    def __enter__(self) -> AuditLog:
        """Enter the context manager and return self."""
        return self

    def __exit__(self, *exc_info: Any) -> None:
        """Exit the context manager, closing the SQLite connection."""
        self.close()

    def __del__(self) -> None:
        """Best-effort close on garbage collection."""
        self.close()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _row_to_entry(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        entry_id=int(row["entry_id"]),
        timestamp_utc=str(row["timestamp_utc"]),
        identifier=str(row["identifier"]),
        method=str(row["method"]),
        score=(float(row["score"]) if row["score"] is not None else None),
        flagged=bool(row["flagged"]),
        payload_json=str(row["payload_json"]),
        prev_hash=str(row["prev_hash"]),
        entry_hash=str(row["entry_hash"]),
    )


@contextmanager
def open_log(db_path: str | Path | None = None) -> Iterable[AuditLog]:
    """Open an :class:`AuditLog` as a context manager."""
    log = AuditLog(db_path=db_path)
    try:
        yield log
    finally:
        log.close()


__all__ = [
    "AuditEntry",
    "AuditLog",
    "ChainVerification",
    "open_log",
]
