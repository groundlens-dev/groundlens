"""The v2 record goes through the existing hash chain, unchanged.

``audit.py`` was not rewritten for v2: the SQLite schema, the chain
algorithm and ``verify_chain`` are exactly what they were, and the v2
record is simply what now sits in the payload. These tests hold that
line — a v1 entry and a v2 entry in the same log, interleaved, and the
chain still verifies.
"""

from __future__ import annotations

import dataclasses
import json

from groundlens.audit import V2_METHOD, AuditLog
from groundlens.audit_record import record_sha256, to_jsonable
from groundlens.types import Decision

from ._sample import SAMPLE_METADATA, build_sample_record

_TS = "2026-08-08T00:00:00+00:00"


def test_record_v2_writes_an_entry_and_the_chain_verifies() -> None:
    record = build_sample_record()
    with AuditLog() as log:
        entry = log.record_v2(identifier="req_001", record=record, timestamp_utc=_TS)
        assert entry.method == V2_METHOD
        assert entry.score is None
        assert entry.flagged is (record.decision is Decision.ESCALATE)
        assert log.verify_chain().valid


def test_payload_carries_the_record_and_its_digest() -> None:
    record = build_sample_record()
    with AuditLog() as log:
        entry = log.record_v2(identifier="req_001", record=record, timestamp_utc=_TS)
        payload = json.loads(entry.payload_json)

    assert payload["inputs"] == to_jsonable(record)
    assert payload["metadata"]["record_sha256"] == record_sha256(record)


def test_metadata_values_never_reach_the_log() -> None:
    record = build_sample_record()
    with AuditLog() as log:
        entry = log.record_v2(identifier="req_001", record=record, timestamp_utc=_TS)

    for value in SAMPLE_METADATA.values():
        assert value not in entry.payload_json


def test_v1_and_v2_entries_share_one_chain() -> None:
    record = build_sample_record()
    with AuditLog() as log:
        log.record(identifier="legacy", method="sgi", flagged=False, score=1.23)
        log.record_v2(identifier="req_001", record=record, timestamp_utc=_TS)
        log.record(identifier="legacy_2", method="dgi", flagged=True, score=0.4)
        log.record_v2(identifier="req_002", record=record, timestamp_utc=_TS)

        verification = log.verify_chain()
        assert verification.valid
        assert verification.entries_checked == 4


def test_tampering_with_a_v2_payload_breaks_the_chain() -> None:
    record = build_sample_record()
    with AuditLog() as log:
        log.record_v2(identifier="req_001", record=record, timestamp_utc=_TS)
        log.record_v2(identifier="req_002", record=record, timestamp_utc=_TS)

        log._conn.execute(
            "UPDATE audit_entries SET payload_json = ? WHERE entry_id = 1",
            (json.dumps({"inputs": {"decision": "clear"}}),),
        )

        verification = log.verify_chain()
        assert not verification.valid
        assert verification.broken_at_entry_id == 1


def test_two_writes_of_the_same_record_have_the_same_record_digest() -> None:
    """The chain hash mixes in a timestamp; the record digest does not."""
    record = build_sample_record()
    with AuditLog() as log:
        first = log.record_v2(
            identifier="req_001", record=record, timestamp_utc="2026-08-08T00:00:00+00:00"
        )
        second = log.record_v2(
            identifier="req_001", record=record, timestamp_utc="2026-09-09T00:00:00+00:00"
        )

    assert first.entry_hash != second.entry_hash
    digests = {json.loads(e.payload_json)["metadata"]["record_sha256"] for e in (first, second)}
    assert len(digests) == 1


def test_flag_can_be_overridden() -> None:
    record = dataclasses.replace(build_sample_record(), decision=Decision.CLEAR)
    with AuditLog() as log:
        entry = log.record_v2(identifier="req_001", record=record, flagged=True, timestamp_utc=_TS)
    assert entry.flagged is True
