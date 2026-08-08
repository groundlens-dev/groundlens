"""Run the YAML fixture corpus through the extractor.

The corpus is the contract with the domain, not with the code: each entry says
"this text contains this claim", in the words a compliance reviewer would use.
Adding a failure mode should be a YAML diff, not a Python one.
"""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from .conftest import CORPUS_DIR, make_profile

pytestmark = pytest.mark.filterwarnings("error")

_PROFILE_SPECS = {
    "eu-es": {
        "decimal_separator": ",",
        "group_separator": ".",
        "date_order": "DMY",
        "currency": "EUR",
    },
    "en-us": {
        "decimal_separator": ".",
        "group_separator": ",",
        "date_order": "MDY",
        "currency": "USD",
    },
    "en-gb": {
        "decimal_separator": ".",
        "group_separator": ",",
        "date_order": "DMY",
        "currency": "GBP",
    },
}


def _load_cases():
    cases = []
    for path in sorted(CORPUS_DIR.glob("*.yaml")):
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for entry in entries:
            cases.append(pytest.param(entry, id=f"{path.stem}::{entry['id']}"))
    return cases


CASES = _load_cases()


def test_corpus_is_not_empty():
    assert len(CASES) >= 60


def _profile(name):
    return make_profile(name, **_PROFILE_SPECS[name])


def _find(facts, expected, text):
    """Locate the fact an expectation refers to, or return None."""
    for fact in facts:
        if fact.kind.value != expected["kind"]:
            continue
        if "raw" in expected and fact.raw != expected["raw"]:
            continue
        if "normalised" in expected and fact.normalised != expected["normalised"]:
            continue
        attrs = dict(fact.attrs)
        wanted = expected.get("attrs") or {}
        if any(attrs.get(key) != value for key, value in wanted.items()):
            continue
        ambiguity = set(attrs.get("ambiguity", "").split(",")) - {""}
        if not set(expected.get("ambiguity") or []) <= ambiguity:
            continue
        assert fact.raw == text[fact.span[0] : fact.span[1]]
        return fact
    return None


@pytest.mark.parametrize("case", CASES)
def test_corpus_case(case):
    from groundlens.facts import extract_facts

    profile = _profile(case["locale"])
    text = case["text"]
    facts = extract_facts(
        text,
        locale=profile,
        reference_date=date.fromisoformat(case["reference_date"]),
    )

    rendered = "\n".join(
        f"  {f.kind.value} {f.raw!r} -> {f.normalised!r} {dict(f.attrs)}" for f in facts
    )

    for expected in case.get("expect") or []:
        found = _find(facts, expected, text)
        assert found is not None, f"missing {expected} in:\n{rendered}"

    for forbidden in case.get("forbid") or []:
        assert not [f for f in facts if f.kind.value == forbidden["kind"]], (
            f"unexpected {forbidden['kind']} in:\n{rendered}"
        )

    for value in case.get("forbid_normalised") or []:
        assert not [f for f in facts if f.normalised == value], (
            f"unexpected {value} in:\n{rendered}"
        )

    for key in case.get("forbid_attrs") or []:
        for fact in facts:
            assert key not in dict(fact.attrs), f"unexpected attr {key} in:\n{rendered}"

    if case.get("exact"):
        assert len(facts) == len(case["expect"]), f"expected an exact set, got:\n{rendered}"


@pytest.mark.parametrize("case", CASES)
def test_corpus_spans_are_exact_substrings(case):
    from groundlens.facts import extract_facts

    profile = _profile(case["locale"])
    text = case["text"]
    facts = extract_facts(
        text,
        locale=profile,
        reference_date=date.fromisoformat(case["reference_date"]),
    )
    for fact in facts:
        start, end = fact.span
        assert 0 <= start < end <= len(text)
        assert fact.raw == text[start:end]


@pytest.mark.parametrize("case", CASES)
def test_corpus_attrs_are_sorted_strings(case):
    from groundlens.facts import extract_facts

    profile = _profile(case["locale"])
    facts = extract_facts(
        case["text"],
        locale=profile,
        reference_date=date.fromisoformat(case["reference_date"]),
    )
    for fact in facts:
        keys = [key for key, _ in fact.attrs]
        assert keys == sorted(keys)
        assert all(isinstance(key, str) and isinstance(value, str) for key, value in fact.attrs)
