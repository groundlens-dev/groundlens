"""Rule 5 and rule 7: the same run serialises to the same bytes.

Input order is an accident of retrieval, of dict literals, of set
iteration. None of it may reach the output. These tests build the same
logical record from inputs supplied in different orders and assert the
canonical JSON is byte-identical, then repeat the build in subprocesses
with different ``PYTHONHASHSEED`` values to prove nothing downstream
depends on Python's string hash randomisation.
"""

from __future__ import annotations

import json

from groundlens.audit_record import canonical_json, record_sha256

from ._helpers import record_digest_in_subprocess
from ._sample import build_sample_record


def test_permuted_inputs_produce_identical_bytes() -> None:
    straight = canonical_json(build_sample_record())
    permuted = canonical_json(build_sample_record(permute=True))
    assert straight == permuted


def test_permuted_inputs_produce_identical_digest() -> None:
    assert record_sha256(build_sample_record()) == record_sha256(build_sample_record(permute=True))


def test_repeated_builds_are_identical() -> None:
    """Ten builds in one process, in case anything caches or mutates."""
    blobs = {canonical_json(build_sample_record()) for _ in range(10)}
    assert len(blobs) == 1


def test_canonical_json_uses_the_contract_serialisation() -> None:
    blob = canonical_json(build_sample_record())
    text = blob.decode("utf-8")
    assert ", " not in text, "separators must be (',', ':') with no spaces"
    assert '": ' not in text
    parsed = json.loads(text)
    assert list(parsed) == sorted(parsed), "top-level keys must be sorted"
    assert parsed["schema"] == "groundlens.audit/2"


def test_non_ascii_is_not_escaped() -> None:
    """``ensure_ascii=False`` is part of the contract, so bytes stay UTF-8."""
    blob = canonical_json(build_sample_record())
    assert b"\\u" not in blob


def test_evidence_sorted_by_id() -> None:
    parsed = json.loads(canonical_json(build_sample_record()))
    ids = [e["id"] for e in parsed["evidence"]]
    assert ids == sorted(ids)


def test_findings_sorted_by_code_then_span_then_rule_id() -> None:
    parsed = json.loads(canonical_json(build_sample_record()))
    keys = [
        (f["code"], tuple(f["span"]) if f["span"] else (-1, -1), f["rule_id"] or "")
        for f in parsed["findings"]
    ]
    assert keys == sorted(keys)


def test_metadata_keys_sorted_and_values_absent() -> None:
    from ._sample import SAMPLE_METADATA

    parsed = json.loads(canonical_json(build_sample_record()))
    assert parsed["metadata_keys"] == sorted(SAMPLE_METADATA)
    blob = canonical_json(build_sample_record()).decode("utf-8")
    for value in SAMPLE_METADATA.values():
        assert value not in blob, "metadata values must never reach the record"


def test_digest_is_independent_of_pythonhashseed() -> None:
    digests = {
        record_digest_in_subprocess({"PYTHONHASHSEED": seed})
        for seed in ("0", "1", "12345", "random")
    }
    assert len(digests) == 1, f"PYTHONHASHSEED changed the record: {digests}"


def test_digest_matches_in_process_value() -> None:
    assert record_digest_in_subprocess({"PYTHONHASHSEED": "0"}) == record_sha256(
        build_sample_record()
    )
