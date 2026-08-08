"""The committed golden record: one fixture, diffed byte for byte.

Everything else in this suite proves a property. This proves a value.
The bytes in ``golden/record.json`` were produced by one host on one
day, and every run since has to reproduce them exactly: the same
normalisation, the same hashes, the same key order, the same separators,
the same UTF-8.

When this test fails, the record format changed. That is either a bug
or a schema bump; it is never a reason to refresh the fixture without
reading the diff. Regenerate deliberately with::

    python tests/determinism/export_golden.py tests/determinism/golden/record.json
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from groundlens.audit_record import canonical_json, record_sha256

from ._sample import build_sample_record

GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "record.json"

GOLDEN_TRAILER = b"\n"
"""The fixture is the canonical bytes plus one line feed.

The record itself has no trailing newline. The file does, so the
``end-of-file-fixer`` pre-commit hook has nothing to fix; a hook that
silently rewrites the fixture would turn this test into a rubber stamp.
Every comparison below accounts for exactly this one byte and no other
difference."""

GOLDEN_SHA256 = "28424d3b42f43e232561f2d539a6a743207a58e4f1440f630eb6c62e9af058b2"
"""Digest of the golden bytes, duplicated here so a corrupted fixture
file cannot make the test pass by agreeing with itself."""


def test_golden_fixture_exists() -> None:
    assert GOLDEN_PATH.is_file(), f"missing golden fixture at {GOLDEN_PATH}"


def test_rebuilt_record_matches_golden_bytes() -> None:
    expected = GOLDEN_PATH.read_bytes()
    actual = canonical_json(build_sample_record()) + GOLDEN_TRAILER

    if actual != expected:
        # A raw bytes assertion prints two unreadable walls. Show the
        # first divergence and the parsed diff instead.
        index = next(
            (i for i, (a, b) in enumerate(zip(actual, expected, strict=False)) if a != b),
            min(len(actual), len(expected)),
        )
        context = slice(max(0, index - 60), index + 60)
        raise AssertionError(
            "golden record mismatch at byte "
            f"{index}\n  expected: ...{expected[context].decode('utf-8', 'replace')}..."
            f"\n  actual:   ...{actual[context].decode('utf-8', 'replace')}..."
        )


def test_golden_bytes_have_the_expected_digest() -> None:
    body = GOLDEN_PATH.read_bytes().removesuffix(GOLDEN_TRAILER)
    assert hashlib.sha256(body).hexdigest() == GOLDEN_SHA256


def test_rebuilt_record_has_the_expected_digest() -> None:
    assert record_sha256(build_sample_record()) == GOLDEN_SHA256


def test_golden_is_valid_json_with_the_contract_shape() -> None:
    parsed = json.loads(GOLDEN_PATH.read_bytes().decode("utf-8"))
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
    assert parsed["library_version"] == "2.0.0"
    assert parsed["determinism"]["unicode_form"] == "NFKC"
    assert parsed["decision"] in {"clear", "escalate"}
    assert set(parsed["counts"]) == {
        "facts_extracted",
        "facts_matched",
        "facts_unmatched",
        "facts_contradicted",
        "rules_evaluated",
        "rules_failed",
    }


def test_golden_file_ends_with_exactly_one_newline() -> None:
    """One trailing newline, and nothing else outside the canonical bytes."""
    raw = GOLDEN_PATH.read_bytes()
    assert raw.endswith(GOLDEN_TRAILER)
    assert not raw.removesuffix(GOLDEN_TRAILER).endswith(b"\n")
    assert b"\r" not in raw, "the fixture must not be checked out with CRLF endings"
