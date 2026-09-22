# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""GroundLens Verification Suite: interoperability.

A record is only trustworthy if someone other than its maker can verify it. This
runs one sealed record through three separate verifiers and shows they agree, then
tampers with the record and shows all three reject it.

    Python API            groundlens' own Record.verify()
    Command line          the `groundlens record verify` CLI, a separate process
    Independent verifier  from-scratch code that shares nothing with the engine:
                          it recomputes the hashes with hashlib and checks the
                          Ed25519 signature with `cryptography`, from the record
                          format alone (canonical JSON, SHA-256, Ed25519)

    pip install "groundlens" cryptography
    python suite/interoperability.py           # human report
    python suite/interoperability.py --json    # machine-readable
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from groundlens import Record, verify
from groundlens.record import IntegrityError

SEED = "00" * 31 + "01"


# --- The independent verifier: no groundlens engine, only the record format. ---
def independent_verify(raw: dict) -> None:
    """Raise ValueError unless the record is internally consistent and signed.

    Recomputes content_hash (canonical JSON + SHA-256), record_hash
    (SHA-256 over content_hash, previous, record_id, timestamp) and checks the
    Ed25519 signature over the record_hash. RFC 8785 canonical JSON, FIPS 180-4
    SHA-256, RFC 8032 Ed25519.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    canon = json.dumps(raw["content"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    content_hash = "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()
    if content_hash != raw["content_hash"]:
        raise ValueError("content_hash mismatch")

    prev = raw.get("previous_record_hash") or ""
    material = f'{raw["content_hash"]}\n{prev}\n{raw["record_id"]}\n{raw["timestamp"]}'
    record_hash = "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
    if record_hash != raw["record_hash"]:
        raise ValueError("record_hash mismatch")

    pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(raw["signer_public_key"]))
    pk.verify(bytes.fromhex(raw["signature"]), raw["record_hash"].encode("utf-8"))


def _python_ok(record: Record) -> bool:
    try:
        record.verify()
        return True
    except IntegrityError:
        return False


def _cli_ok(record: Record) -> bool:
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "record.jsonl"
        log.write_text(record.to_json() + "\n")
        p = subprocess.run(["groundlens", "record", "verify", str(log)],
                           capture_output=True, text=True)
        return p.returncode == 0


def _independent_ok(record: Record) -> bool:
    try:
        independent_verify(json.loads(record.to_json()))
        return True
    except Exception:
        return False


def _tampered(record: Record) -> Record:
    d = json.loads(record.to_json())
    d["content"]["outcome"]["decision"] = "PASS"  # was FAIL
    return Record.from_json(json.dumps(d))


def run():
    genuine = verify("Revenue was EUR 15M.", [("10k", "Revenue was EUR 10M.")],
                     signing_key=SEED, lexical=False)
    forged = _tampered(genuine)
    verifiers = {"Python API": _python_ok, "Command line": _cli_ok, "Independent verifier": _independent_ok}
    accepts = {name: fn(genuine) for name, fn in verifiers.items()}
    rejects = {name: (not fn(forged)) for name, fn in verifiers.items()}
    return {
        "genuine_accepted_by_all": all(accepts.values()),
        "tampered_rejected_by_all": all(rejects.values()),
        "accepts": accepts,
        "rejects_tampered": rejects,
    }


def main(argv):
    r = run()
    ok = r["genuine_accepted_by_all"] and r["tampered_rejected_by_all"]
    if "--json" in argv:
        print(json.dumps({"suite": "interoperability", "pass": ok, **r}, indent=2))
        return 0 if ok else 1
    print("GroundLens Verification Interoperability\n")
    print("  A genuine record, verified by three independent verifiers:")
    for name, good in r["accepts"].items():
        print(f"    [{'  ok  ' if good else ' FAIL '}] {name} accepts the genuine record")
    print("\n  A tampered record (decision flipped), rejected by all three:")
    for name, good in r["rejects_tampered"].items():
        print(f"    [{'  ok  ' if good else ' FAIL '}] {name} rejects the tampered record")
    print("\n" + ("PORTABLE AND INDEPENDENTLY VERIFIABLE" if ok else "INTEROP CHECK FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
