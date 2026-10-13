# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Verifier.check(): signed by a key service, stored before it returns.

The key services and stores are stand-ins with the same call shapes as
boto3, azure-keyvault-keys, azure-storage-blob and a DB-API connection.
The P-256 signer below is a small pure-Python implementation, for tests only,
so the suite needs no cryptography package.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

import groundlens as gl
from groundlens.record import IntegrityError, Record
from groundlens.sinks import ChainConflict, StoreError

# ---- a P-256 key, for tests ----------------------------------------------------------

P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (
    0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
    0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5,
)


def _add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % P == 0:
        return None
    if a == b:
        m = (3 * a[0] * a[0] - 3) * pow(2 * a[1], -1, P) % P
    else:
        m = (b[1] - a[1]) * pow(b[0] - a[0], -1, P) % P
    x = (m * m - a[0] - b[0]) % P
    return (x, (m * (a[0] - x) - a[1]) % P)


def _mul(k, point=G):
    out = None
    while k:
        if k & 1:
            out = _add(out, point)
        point = _add(point, point)
        k >>= 1
    return out


class P256Key:
    def __init__(self, secret: int) -> None:
        self.d = secret
        x, y = _mul(secret)
        self.point = b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")

    def spki_der(self) -> bytes:
        prefix = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")
        return prefix + self.point

    def sign_raw(self, message: bytes) -> bytes:
        z = int.from_bytes(hashlib.sha256(message).digest(), "big")
        k = int.from_bytes(hmac.new(self.d.to_bytes(32, "big"), message, hashlib.sha256).digest(), "big") % N or 1
        r = _mul(k)[0] % N
        s = pow(k, -1, N) * (z + r * self.d) % N
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")

    def sign_der(self, message: bytes) -> bytes:
        raw = self.sign_raw(message)

        def integer(b: bytes) -> bytes:
            b = b.lstrip(b"\x00")
            if b[0] & 0x80:
                b = b"\x00" + b
            return b"\x02" + bytes([len(b)]) + b

        body = integer(raw[:32]) + integer(raw[32:])
        return b"\x30" + bytes([len(body)]) + body


KEY = P256Key(0x1234567890ABCDEF)

# ---- stand-ins for the services ---------------------------------------------------------


class FakeKms:
    def get_public_key(self, KeyId):  # noqa: N803 - boto3 argument names
        return {"KeyId": KeyId, "KeySpec": "ECC_NIST_P256", "PublicKey": KEY.spki_der()}

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):  # noqa: N803
        assert (MessageType, SigningAlgorithm) == ("RAW", "ECDSA_SHA_256")
        return {"KeyId": KeyId, "Signature": KEY.sign_der(Message)}


class FakeKeyVault:
    """CryptographyClient.sign(algorithm, digest) over a precomputed digest."""

    def sign(self, algorithm, digest):
        assert algorithm == "ES256"
        z = int.from_bytes(digest, "big")
        k = 0xC0FFEE
        r = _mul(k)[0] % N
        s = pow(k, -1, N) * (z + r * KEY.d) % N
        return SimpleNamespace(signature=r.to_bytes(32, "big") + s.to_bytes(32, "big"))


KEY_VAULT_KEY = SimpleNamespace(key=SimpleNamespace(crv=SimpleNamespace(value="P-256"), x=KEY.point[1:33], y=KEY.point[33:]))

ANSWER = "Revenue was €10M."
PASSAGES = [("10k#p1", "Revenue was €10M.")]

# ---- signers ----------------------------------------------------------------------------


@pytest.mark.parametrize("signer", [gl.signers.aws_kms(FakeKms(), "alias/gl"), gl.signers.azure_key_vault(FakeKeyVault(), KEY_VAULT_KEY)])
def test_a_key_service_signs_and_the_record_verifies_offline(tmp_path, signer):
    v = gl.Verifier(signer=signer, sink=gl.sinks.jsonl(tmp_path))
    first = v.check(answer=ANSWER, passages=PASSAGES)
    second = v.check(answer="Revenue was €15M.", passages=PASSAGES)
    assert (first.decision, second.decision) == ("PASS", "FAIL")
    assert first.signature_algorithm == "ecdsa-p256-sha256"
    assert first.signer_public_key == KEY.point.hex()
    assert second.previous_record_hash == first.record_hash
    stored = Record.read_log(tmp_path / "records.jsonl")
    assert [r.record_hash for r in stored] == [first.record_hash, second.record_hash]
    assert Record.verify_chain(stored) == 2

    tampered = dict(first.raw, signature=second.raw["signature"])
    with pytest.raises(IntegrityError):
        Record(tampered).verify()


def test_a_key_service_with_the_wrong_key_is_refused_before_a_record_exists(tmp_path):
    class WrongKey(FakeKms):
        def get_public_key(self, KeyId):  # noqa: N803
            return {"KeySpec": "ECC_NIST_P256", "PublicKey": P256Key(99).spki_der()}

    v = gl.Verifier(signer=gl.signers.aws_kms(WrongKey(), "k"), sink=gl.sinks.jsonl(tmp_path))
    with pytest.raises(ValueError, match="refused"):
        v.check(answer=ANSWER, passages=PASSAGES)
    assert not (tmp_path / "records.jsonl").exists()


def test_a_kms_key_of_another_type_is_rejected():
    class Rsa(FakeKms):
        def get_public_key(self, KeyId):  # noqa: N803
            return {"KeySpec": "RSA_2048", "PublicKey": b"..."}

    with pytest.raises(ValueError, match="ECC_NIST_P256"):
        gl.signers.aws_kms(Rsa(), "k").public_key()


def test_a_local_key_signs_every_record_with_the_same_key(tmp_path):
    key = gl.signers.local_key()
    v = gl.Verifier(signer=key, sink=gl.sinks.jsonl(tmp_path / "chain.jsonl"))
    a = v.check(answer=ANSWER, passages=PASSAGES)
    b = v.check(answer=ANSWER, passages=PASSAGES)
    assert a.signer_public_key == b.signer_public_key
    assert a.signature_algorithm == "ed25519"
    assert "signature_algorithm" not in a.raw


# ---- check() stores before it returns -------------------------------------------------


def test_check_needs_a_sink_and_returns_no_decision_when_storing_fails(tmp_path):
    with pytest.raises(ValueError, match="sink"):
        gl.Verifier().check(answer=ANSWER, passages=PASSAGES)

    class Broken:
        def head(self):
            return None

        def append(self, record):
            raise StoreError("disk full")

        def records(self):
            return []

    with pytest.raises(StoreError, match="disk full"):
        gl.Verifier(sink=Broken()).check(answer=ANSWER, passages=PASSAGES)


def test_check_reseals_when_another_writer_moved_the_chain(tmp_path):
    sink = gl.sinks.jsonl(tmp_path)
    other = gl.Verifier(sink=sink)

    class Stale:
        """Reports the head as it was before the other writer appended."""

        calls = 0

        def head(self):
            Stale.calls += 1
            if Stale.calls == 1:
                h = sink.head()
                other.check(answer=ANSWER, passages=PASSAGES)
                return h
            return sink.head()

        def append(self, record):
            sink.append(record)

        def records(self):
            return sink.records()

    mine = gl.Verifier(sink=Stale()).check(answer=ANSWER, passages=PASSAGES)
    chain = sink.records()
    assert len(chain) == 2 and chain[-1].record_hash == mine.record_hash
    Record.verify_chain(chain)


def test_a_sink_refuses_a_record_that_does_not_follow_its_head(tmp_path):
    sink = gl.sinks.jsonl(tmp_path)
    v = gl.Verifier()
    sink.append(v.seal(answer=ANSWER, passages=PASSAGES))
    with pytest.raises(ChainConflict):
        sink.append(v.seal(answer=ANSWER, passages=PASSAGES))


# ---- stores --------------------------------------------------------------------------


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts: list[dict] = []

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):  # noqa: N803
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        return {"Contents": [{"Key": k} for k in keys], "IsTruncated": False}

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, **kw):
        self.puts.append(kw)
        if kw.get("IfNoneMatch") == "*" and kw["Key"] in self.objects:
            err = Exception("PreconditionFailed")
            err.response = {"Error": {"Code": "PreconditionFailed"}}
            raise err
        self.objects[kw["Key"]] = kw["Body"]


class FakeContainer:
    def __init__(self):
        self.blobs: dict[str, bytes] = {}

    def list_blobs(self, name_starts_with):
        return [SimpleNamespace(name=n) for n in self.blobs if n.startswith(name_starts_with)]

    def download_blob(self, name):
        return SimpleNamespace(readall=lambda: self.blobs[name])

    def upload_blob(self, name, data, overwrite):
        if name in self.blobs and not overwrite:
            raise type("ResourceExistsError", (Exception,), {})(name)
        self.blobs[name] = data


@pytest.mark.parametrize(
    "make_sink",
    [
        lambda tmp: gl.sinks.s3_object_lock(FakeS3(), "audit", retain_days=2555),
        lambda tmp: gl.sinks.azure_blob(FakeContainer()),
        lambda tmp: gl.sinks.postgres(sqlite3.connect(tmp / "db.sqlite"), paramstyle="qmark"),
        lambda tmp: gl.sinks.jsonl(tmp),
    ],
    ids=["s3", "azure", "postgres", "jsonl"],
)
def test_every_sink_keeps_a_chain_that_verifies(tmp_path, make_sink):
    sink = make_sink(tmp_path)
    v = gl.Verifier(signer=gl.signers.local_key(), sink=sink)
    records = [v.check(answer=ANSWER, passages=PASSAGES) for _ in range(3)]
    assert sink.head() == records[-1].record_hash
    back = sink.records()
    assert [r.record_hash for r in back] == [r.record_hash for r in records]
    assert Record.verify_chain(back) == 3


def test_s3_writes_each_position_once_with_retention():
    s3 = FakeS3()
    sink = gl.sinks.s3_object_lock(s3, "audit", retain_days=10)
    v = gl.Verifier(sink=sink)
    v.check(answer=ANSWER, passages=PASSAGES)
    put = s3.puts[0]
    assert put["Key"] == "groundlens/records/000000000000.json"
    assert (put["IfNoneMatch"], put["ObjectLockMode"]) == ("*", "COMPLIANCE")
    # A second writer that read the same head loses the race and is told so.
    record = v.seal(answer=ANSWER, passages=PASSAGES, previous=None)
    with pytest.raises(ChainConflict):
        sink.append(record)


def test_the_postgres_table_cannot_hold_a_fork(tmp_path):
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    sink = gl.sinks.postgres(conn, paramstyle="qmark")
    first = gl.Verifier().seal(answer=ANSWER, passages=PASSAGES)
    sink.append(first)
    row = "INSERT INTO groundlens_records VALUES ('records', ?, ?, ?, ?, '{}')"
    conn.execute(row, (1, "x", "sha256:x", first.record_hash))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(row, (2, "y", "sha256:y", first.record_hash))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(row, (1, "z", "sha256:z", "sha256:x"))


# ---- several chains -------------------------------------------------------------------


def test_record_verify_accepts_several_chains_and_a_directory(tmp_path):
    for worker in ("worker-1", "worker-2"):
        v = gl.Verifier(sink=gl.sinks.jsonl(tmp_path, chain=worker))
        v.check(answer=ANSWER, passages=PASSAGES)
        v.check(answer=ANSWER, passages=PASSAGES)
    run = subprocess.run([sys.executable, "-m", "groundlens.cli", "record", "verify", str(tmp_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "4 records in 2 chains" in run.stdout

    one = tmp_path / "worker-1.jsonl"
    two = tmp_path / "worker-2.jsonl"
    copy = tmp_path / "copy.jsonl"
    copy.write_text(one.read_text(encoding="utf-8"), encoding="utf-8")
    run = subprocess.run([sys.executable, "-m", "groundlens.cli", "record", "verify", str(one), str(two), str(copy)], capture_output=True, text=True)
    assert run.returncode == 2 and "two chains" in run.stderr
