"""The audit record a real ``check()`` produces has to survive the wire.

``tests/determinism`` proves the record format is deterministic, but it builds
its record by hand.  Nothing proved that the record ``check()`` actually
returns could be serialised at all — and it could not: ``control.py`` was
handing ``audit_record`` plain dictionaries, so ``canonical_json`` died on
``'dict' object has no attribute 'id'`` and ``record_sha256`` with it.  A hash
chain over a payload that cannot be produced is not an audit trail.

These tests run the real extractor, the real matcher and a real shipped pack,
and then take the record all the way out and back: canonical JSON, digest,
re-parse, and into the existing hash chain.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest

from groundlens.audit import AuditLog
from groundlens.audit_record import (
    AuditRecord,
    Counts,
    DeterminismBlock,
    EvidenceDigest,
    FindingRecord,
    PredicateRef,
    RulesetRef,
    canonical_json,
    record_sha256,
    to_jsonable,
)
from groundlens.control import check
from groundlens.types import Decision, Severity

REFERENCE_DATE = datetime.date(2026, 8, 8)
METADATA = {"product_type": "mortgage", "disclosure_set": "es-2026"}

ANSWER = (
    "You must not exceed the limit. The arrangement fee is 1.250,00 EUR and "
    "the term is 12 meses. This information does not constitute advice."
)
EVIDENCE = [
    {"id": "policy#p1", "text": "Customers may exceed the limit with prior approval."},
    {"id": "policy#p2", "text": "La comision de apertura es de 1.250,00 EUR."},
]


def run_check() -> Any:
    return check(
        ANSWER,
        EVIDENCE,
        ruleset="eu-retail-banking",
        metadata=METADATA,
        reference_date=REFERENCE_DATE,
    )


def parse_record(blob: bytes) -> AuditRecord:
    """Rebuild a record from its canonical JSON, with the declared types.

    Deliberately not a helper in ``audit_record``: writing it out here is what
    shows that every field in the wire format maps back onto exactly one typed
    field, with nothing lost and nothing invented.
    """
    raw = json.loads(blob.decode("utf-8"))
    return AuditRecord(
        schema=raw["schema"],
        library_version=raw["library_version"],
        extractor_version=raw["extractor_version"],
        answer_sha256=raw["answer_sha256"],
        evidence=tuple(
            EvidenceDigest(id=item["id"], sha256=item["sha256"]) for item in raw["evidence"]
        ),
        tools_output_sha256=raw["tools_output_sha256"],
        metadata_keys=tuple(raw["metadata_keys"]),
        ruleset=RulesetRef(**raw["ruleset"]),
        predicates=tuple(PredicateRef(**item) for item in raw["predicates"]),
        determinism=DeterminismBlock(
            locale_profile=raw["determinism"]["locale_profile"],
            reference_date=raw["determinism"]["reference_date"],
            unicode_form=raw["determinism"]["unicode_form"],
        ),
        counts=Counts(**raw["counts"]),
        decision=Decision(raw["decision"]),
        findings=tuple(
            FindingRecord(
                code=item["code"],
                severity=Severity(item["severity"]),
                span=None if item["span"] is None else (item["span"][0], item["span"][1]),
                rule_id=item["rule_id"],
                evidence_id=item["evidence_id"],
            )
            for item in raw["findings"]
        ),
    )


# ── The record is typed at the boundary ─────────────────────────────────────


def test_the_record_is_built_from_typed_objects_not_dicts() -> None:
    """The regression itself: dicts here are what broke serialisation."""
    audit = run_check().audit
    assert isinstance(audit, AuditRecord)
    assert isinstance(audit.ruleset, RulesetRef)
    assert isinstance(audit.counts, Counts)
    assert isinstance(audit.determinism, DeterminismBlock)
    assert audit.evidence
    assert all(isinstance(item, EvidenceDigest) for item in audit.evidence)
    assert audit.predicates
    assert all(isinstance(item, PredicateRef) for item in audit.predicates)
    assert audit.findings
    assert all(isinstance(item, FindingRecord) for item in audit.findings)


def test_a_real_result_serialises_and_hashes() -> None:
    audit = run_check().audit
    blob = canonical_json(audit)
    assert isinstance(blob, bytes)
    digest = record_sha256(audit)
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_a_real_record_round_trips_through_canonical_json() -> None:
    audit = run_check().audit
    blob = canonical_json(audit)

    rebuilt = parse_record(blob)

    assert rebuilt == audit
    assert canonical_json(rebuilt) == blob
    assert record_sha256(rebuilt) == record_sha256(audit)


def test_the_record_carries_the_contract_shape() -> None:
    parsed = json.loads(canonical_json(run_check().audit).decode("utf-8"))
    assert set(parsed) == {
        "schema",
        "library_version",
        "extractor_version",
        "answer_sha256",
        "evidence",
        "tools_output_sha256",
        "metadata_keys",
        "ruleset",
        "predicates",
        "determinism",
        "counts",
        "decision",
        "findings",
    }
    assert parsed["schema"] == "groundlens.audit/2"
    assert parsed["determinism"]["unicode_form"] == "NFKC"
    assert parsed["determinism"]["reference_date"] == "2026-08-08"
    assert parsed["metadata_keys"] == ["disclosure_set", "product_type"]


def test_metadata_values_never_reach_the_record() -> None:
    blob = canonical_json(run_check().audit)
    for value in METADATA.values():
        assert value.encode("utf-8") not in blob


def test_the_answer_digest_identifies_the_text_the_spans_point_into() -> None:
    """A hash of a slightly different string proves nothing about this run."""
    from groundlens.audit_record import sha256_text
    from groundlens.determinism import normalise_text

    audit = run_check().audit
    assert audit.answer_sha256 == sha256_text(normalise_text(ANSWER))


# ── Determinism of the whole path ───────────────────────────────────────────


def test_the_same_call_twice_is_byte_identical() -> None:
    first = canonical_json(run_check().audit)
    second = canonical_json(run_check().audit)
    assert first == second
    assert record_sha256(run_check().audit) == record_sha256(run_check().audit)


def test_evidence_order_does_not_change_the_bytes() -> None:
    """Rule 5: evidence is sorted by id at the serialisation boundary."""
    forward = check(
        ANSWER,
        EVIDENCE,
        ruleset="eu-retail-banking",
        metadata=METADATA,
        reference_date=REFERENCE_DATE,
    )
    reversed_ = check(
        ANSWER,
        list(reversed(EVIDENCE)),
        ruleset="eu-retail-banking",
        metadata=METADATA,
        reference_date=REFERENCE_DATE,
    )
    assert canonical_json(forward.audit) == canonical_json(reversed_.audit)


def test_no_float_anywhere_in_a_real_record() -> None:
    def walk(value: object) -> None:
        assert not isinstance(value, float), f"float in the audit record: {value!r}"
        if isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
        elif isinstance(value, list | tuple):
            for item in value:
                walk(item)

    walk(to_jsonable(run_check().audit))


# ── Through the existing hash chain ─────────────────────────────────────────


def test_a_real_record_goes_through_record_v2_and_the_chain_verifies() -> None:
    result = run_check()
    with AuditLog() as log:
        entry = log.record_v2(identifier="req_001", record=result.audit)
        assert entry.score is None
        assert entry.flagged is (result.decision is Decision.ESCALATE)
        assert log.verify_chain().valid

        payload = json.loads(entry.payload_json)
        assert payload["inputs"] == to_jsonable(result.audit)
        assert payload["metadata"]["record_sha256"] == record_sha256(result.audit)


def test_the_chain_still_verifies_with_several_real_records() -> None:
    first = run_check()
    second = check(
        "This information does not constitute advice.",
        [{"id": "policy#p1", "text": "Nothing to declare."}],
        ruleset="eu-retail-banking",
        metadata=METADATA,
        reference_date=REFERENCE_DATE,
    )
    with AuditLog() as log:
        log.record_v2(identifier="req_001", record=first.audit)
        log.record(identifier="legacy", method="sgi", flagged=False, score=1.23)
        log.record_v2(identifier="req_002", record=second.audit)
        assert log.count() == 3
        assert log.verify_chain().valid


def test_metadata_values_never_reach_the_log() -> None:
    result = run_check()
    with AuditLog() as log:
        entry = log.record_v2(identifier="req_001", record=result.audit)
    for value in METADATA.values():
        assert value not in entry.payload_json


# ── The run this whole exercise was about ───────────────────────────────────


def test_the_wedge_case_is_recorded_as_a_contradiction() -> None:
    """Bug 1 and bug 2 meet here: the finding exists *and* it reaches the record."""
    result = run_check()
    codes = [finding.code for finding in result.findings]
    assert "fact.contradicted.obligation" in codes
    assert result.decision is Decision.ESCALATE

    recorded = {finding.code for finding in result.audit.findings}
    assert "fact.contradicted.obligation" in recorded
    assert result.audit.counts.facts_contradicted >= 1


@pytest.mark.parametrize("field", ["evidence", "predicates", "findings"])
def test_every_collection_in_the_record_is_a_tuple(field: str) -> None:
    """Not a list, not a set: the record is immutable and its order is fixed."""
    assert isinstance(getattr(run_check().audit, field), tuple)
