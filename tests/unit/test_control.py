"""Tests for ``groundlens.control.check``.

The fact extractor and matcher are built in parallel (CONTRACT.md section 2).
This module never imports the real ones: it installs a small fake with the
agreed signature so the orchestration, the fail-closed behaviour and the
decision rule can be tested on their own.

``groundlens.types`` and ``groundlens.audit_record`` are hard dependencies of
``control``; the whole module skips until they land.
"""

from __future__ import annotations

import datetime
import hashlib
import re
import sys
import types as pytypes
import unicodedata
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip(
    "groundlens.types",
    reason="groundlens.types is written in parallel (CONTRACT.md section 2)",
)
pytest.importorskip(
    "groundlens.audit_record",
    reason="groundlens.audit_record is written in parallel (CONTRACT.md section 6)",
)

from groundlens.types import (
    Decision,
    Evidence,
    Fact,
    FactKind,
    Match,
    MatchState,
    Severity,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from groundlens.packs.loader import Pack


# ── The fake extractor and matcher ──────────────────────────────────────────

_CURRENCY_RE = re.compile(r"€\s?\d+(?:[.,]\d+)*")
_CITATION_RE = re.compile(r"\[([^\]]+)\]")
_OBLIGATION_RE = re.compile(r"\b(must not|must|may|should)\b", re.IGNORECASE)


def fake_extract_facts(
    text: str,
    *,
    locale: str,
    reference_date: datetime.date | None,
    config: Mapping[str, Mapping[str, str]],
) -> tuple[Fact, ...]:
    """Stand-in for ``groundlens.facts.extract_facts``.

    Deliberately crude. Its job is to produce well-formed Facts with spans
    into the already-normalised text, not to be a real extractor.
    """
    del locale, reference_date, config
    facts: list[Fact] = []
    for match in _CURRENCY_RE.finditer(text):
        facts.append(
            Fact(
                kind=FactKind.CURRENCY,
                raw=match.group(0),
                span=match.span(),
                normalised=re.sub(r"[^\d]", "", match.group(0)),
            )
        )
    for match in _CITATION_RE.finditer(text):
        facts.append(
            Fact(
                kind=FactKind.CITATION,
                raw=match.group(0),
                span=match.span(),
                normalised=match.group(1),
            )
        )
    for match in _OBLIGATION_RE.finditer(text):
        polarity = match.group(1).lower().replace(" ", "_")
        facts.append(
            Fact(
                kind=FactKind.OBLIGATION,
                raw=match.group(0),
                span=match.span(),
                normalised=polarity,
                attrs=(("polarity", polarity),),
            )
        )
    return tuple(facts)


def fake_match_facts(
    facts: tuple[Fact, ...],
    evidence: tuple[Evidence, ...],
    *,
    locale: str,
    config: Mapping[str, Mapping[str, str]],
) -> tuple[Match, ...]:
    """Stand-in for ``groundlens.facts.match_facts``."""
    del locale, config
    matches: list[Match] = []
    for fact in facts:
        state = MatchState.UNMATCHED
        evidence_id: str | None = None
        evidence_value: str | None = None
        for item in evidence:
            if fact.kind is FactKind.CITATION and fact.normalised == item.id:
                state, evidence_id = MatchState.MATCHED, item.id
                break
            if fact.kind is FactKind.OBLIGATION:
                found = _OBLIGATION_RE.search(item.text)
                if found is None:
                    continue
                supported = found.group(1).lower().replace(" ", "_")
                evidence_id = item.id
                if supported == fact.normalised:
                    state = MatchState.MATCHED
                else:
                    state, evidence_value = MatchState.CONTRADICTED, supported
                break
            if fact.normalised and fact.normalised in re.sub(r"[^\d]", "", item.text):
                state, evidence_id = MatchState.MATCHED, item.id
                break
        matches.append(
            Match(
                fact=fact,
                state=state,
                evidence_id=evidence_id,
                evidence_value=evidence_value,
            )
        )
    return tuple(matches)


if "groundlens.facts" not in sys.modules:
    try:  # pragma: no cover - depends on which agent landed first
        import groundlens.facts  # noqa: F401
    except ImportError:  # pragma: no cover
        _fake_module = pytypes.ModuleType("groundlens.facts")
        _fake_module.extract_facts = fake_extract_facts  # type: ignore[attr-defined]
        _fake_module.match_facts = fake_match_facts  # type: ignore[attr-defined]
        _fake_module.EXTRACTOR_VERSION = "fake"  # type: ignore[attr-defined]
        sys.modules["groundlens.facts"] = _fake_module

from groundlens import control  # noqa: E402
from groundlens.packs.loader import load_pack  # noqa: E402


@pytest.fixture(autouse=True)
def _use_the_fake_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Always run against the fake, even once the real module lands."""
    monkeypatch.setattr(control, "extract_facts", fake_extract_facts)
    monkeypatch.setattr(control, "match_facts", fake_match_facts)


# ── Fixtures ────────────────────────────────────────────────────────────────

DISCLOSURE = "This information does not constitute advice."

FULL_METADATA: dict[str, str] = {"product_type": "mortgage", "disclosure_set": "es-2026"}
REFERENCE_DATE = datetime.date(2026, 8, 8)


@pytest.fixture
def banking_pack() -> Pack:
    return load_pack("eu-retail-banking")


def run(
    answer: str,
    evidence: Sequence[Any],
    *,
    ruleset: Any,
    metadata: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    return control.check(
        answer,
        evidence,
        ruleset=ruleset,
        metadata=FULL_METADATA if metadata is None else metadata,
        reference_date=REFERENCE_DATE,
        **kwargs,
    )


def fullwidth(text: str) -> str:
    """Render ASCII as fullwidth forms, which NFKC folds back to ASCII."""
    return "".join(chr(ord(char) - 0x20 + 0xFF00) if " " < char <= "~" else char for char in text)


def audit_field(audit: object, name: str) -> Any:
    if not hasattr(audit, name):
        pytest.skip(f"the audit record does not expose {name!r} yet")
    return getattr(audit, name)


# ── Evidence shapes ─────────────────────────────────────────────────────────


def test_a_bare_string_of_evidence_is_refused(banking_pack: Pack) -> None:
    with pytest.raises(TypeError) as excinfo:
        run("anything", "a policy document", ruleset=banking_pack)
    message = str(excinfo.value)
    assert "id" in message
    assert "source" in message


def test_a_string_inside_the_sequence_is_refused(banking_pack: Pack) -> None:
    with pytest.raises(TypeError, match="evidence\\[1\\] is a bare string"):
        run(
            "anything",
            [{"id": "a", "text": "x"}, "a policy document"],
            ruleset=banking_pack,
        )


def test_evidence_without_an_id_is_refused(banking_pack: Pack) -> None:
    with pytest.raises(TypeError, match="missing 'id'"):
        run("anything", [{"text": "x"}], ruleset=banking_pack)


def test_evidence_with_a_stray_key_is_refused(banking_pack: Pack) -> None:
    with pytest.raises(TypeError, match="unexpected key"):
        run("anything", [{"id": "a", "text": "x", "score": "0.9"}], ruleset=banking_pack)


def test_duplicate_evidence_ids_are_refused(banking_pack: Pack) -> None:
    with pytest.raises(ValueError, match="more than once"):
        run(
            "anything",
            [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}],
            ruleset=banking_pack,
        )


def test_evidence_objects_are_accepted(banking_pack: Pack) -> None:
    result = run(DISCLOSURE, [Evidence(id="a", text="x")], ruleset=banking_pack)
    assert result.decision is Decision.CLEAR


def test_empty_evidence_is_reported(banking_pack: Pack) -> None:
    result = run(DISCLOSURE, [], ruleset=banking_pack)
    codes = [finding.code for finding in result.findings]
    assert "evidence.empty" in codes


def test_answer_must_be_a_string(banking_pack: Pack) -> None:
    with pytest.raises(TypeError, match="answer must be a string"):
        run(None, [], ruleset=banking_pack)  # type: ignore[arg-type]


# ── Fail closed ─────────────────────────────────────────────────────────────


def test_missing_required_metadata_escalates(banking_pack: Pack) -> None:
    result = run(DISCLOSURE, [], ruleset=banking_pack, metadata={})
    assert result.decision is Decision.ESCALATE
    missing = [f for f in result.findings if f.code == "pack.metadata.missing"]
    assert len(missing) == 2
    assert all(finding.severity is Severity.FAIL for finding in missing)


@pytest.mark.parametrize("dropped", ["product_type", "disclosure_set"])
def test_each_required_key_fails_closed_on_its_own(banking_pack: Pack, dropped: str) -> None:
    metadata = {key: value for key, value in FULL_METADATA.items() if key != dropped}
    result = run(DISCLOSURE, [], ruleset=banking_pack, metadata=metadata)
    assert result.decision is Decision.ESCALATE
    missing = [f for f in result.findings if f.code == "pack.metadata.missing"]
    assert len(missing) == 1
    assert dropped in missing[0].message


def test_metadata_none_is_the_same_as_empty(banking_pack: Pack) -> None:
    result = control.check(
        DISCLOSURE,
        [],
        ruleset=banking_pack,
        metadata=None,
        reference_date=REFERENCE_DATE,
    )
    assert result.decision is Decision.ESCALATE


def test_check_takes_no_argument_that_relaxes_anything() -> None:
    import inspect

    parameters = inspect.signature(control.check).parameters
    assert set(parameters) == {
        "answer",
        "evidence",
        "ruleset",
        "tools_output",
        "metadata",
        "reference_date",
        "registry",
    }


# ── The decision rule ───────────────────────────────────────────────────────


def test_a_grounded_answer_clears(banking_pack: Pack) -> None:
    answer = f"The monthly payment is €450. {DISCLOSURE}"
    result = run(
        answer,
        [{"id": "policy#p1", "text": "Monthly payment: €450 for this product."}],
        ruleset=banking_pack,
    )
    assert result.decision is Decision.CLEAR
    assert all(finding.severity is not Severity.FAIL for finding in result.findings)


def test_an_amount_absent_from_the_evidence_escalates(banking_pack: Pack) -> None:
    answer = f"The monthly payment is €999. {DISCLOSURE}"
    result = run(
        answer,
        [{"id": "policy#p1", "text": "Monthly payment: €450 for this product."}],
        ruleset=banking_pack,
    )
    assert result.decision is Decision.ESCALATE
    unmatched = [f for f in result.findings if f.code == "fact.unmatched.currency"]
    assert len(unmatched) == 1
    assert unmatched[0].rule_id == "BNK-001"
    assert unmatched[0].fact is not None
    assert unmatched[0].fact.raw == "€999"


def test_decision_language_escalates(banking_pack: Pack) -> None:
    answer = f"Your application is approved. {DISCLOSURE}"
    result = run(answer, [{"id": "a", "text": "x"}], ruleset=banking_pack)
    assert result.decision is Decision.ESCALATE
    assert any(finding.rule_id == "BNK-014" for finding in result.findings)


def test_a_missing_disclosure_escalates(banking_pack: Pack) -> None:
    result = run("All is well.", [{"id": "a", "text": "x"}], ruleset=banking_pack)
    assert result.decision is Decision.ESCALATE
    assert any(finding.rule_id == "BNK-031" for finding in result.findings)


def test_overstated_obligation_escalates(banking_pack: Pack) -> None:
    answer = f"You must pay the fee. {DISCLOSURE}"
    result = run(
        answer,
        [{"id": "policy#p1", "text": "The customer should pay the fee."}],
        ruleset=banking_pack,
    )
    assert result.decision is Decision.ESCALATE
    assert any(finding.rule_id == "BNK-020" for finding in result.findings)


def test_warnings_alone_do_not_escalate(banking_pack: Pack) -> None:
    result = run(DISCLOSURE, [{"id": "a", "text": "x"}], ruleset=banking_pack)
    assert any(finding.severity is Severity.WARN for finding in result.findings)
    assert result.decision is Decision.CLEAR


def test_the_result_carries_no_score(banking_pack: Pack) -> None:
    result = run(DISCLOSURE, [{"id": "a", "text": "x"}], ruleset=banking_pack)
    for forbidden in ("score", "confidence", "probability", "quality"):
        assert not hasattr(result, forbidden)


# ── Ordering, normalisation and determinism ─────────────────────────────────


def test_findings_are_sorted_by_code_then_span_then_rule(banking_pack: Pack) -> None:
    answer = f"Your application is approved: €999 and €998. {DISCLOSURE}"
    result = run(answer, [{"id": "a", "text": "nothing"}], ruleset=banking_pack)
    keys = [
        (
            finding.code,
            finding.fact.span if finding.fact is not None else (-1, -1),
            finding.rule_id or "",
        )
        for finding in result.findings
    ]
    assert keys == sorted(keys)


def test_the_same_inputs_give_the_same_findings(banking_pack: Pack) -> None:
    answer = f"The payment is €999. {DISCLOSURE}"
    evidence = [{"id": "b", "text": "x"}, {"id": "a", "text": "y"}]
    first = run(answer, evidence, ruleset=banking_pack)
    second = run(answer, list(reversed(evidence)), ruleset=banking_pack)
    assert first.findings == second.findings
    assert first.decision == second.decision


def test_nfkc_is_applied_once_on_input(banking_pack: Pack) -> None:
    answer = fullwidth("The fee is") + " €450."
    result = run(answer, [{"id": "a", "text": "€450"}], ruleset=banking_pack)
    expected = hashlib.sha256(unicodedata.normalize("NFKC", answer).encode("utf-8")).hexdigest()
    assert audit_field(result.audit, "answer_sha256") == expected


def test_spans_index_into_the_normalised_answer(banking_pack: Pack) -> None:
    answer = fullwidth("Fee") + " €999 today."
    normalised = unicodedata.normalize("NFKC", answer)
    result = run(answer, [{"id": "a", "text": "nothing"}], ruleset=banking_pack)
    unmatched = [f for f in result.findings if f.code == "fact.unmatched.currency"]
    assert unmatched
    start, end = unmatched[0].fact.span
    assert normalised[start:end] == "€999"


# ── The reference date ──────────────────────────────────────────────────────


def test_a_pack_that_reads_relative_dates_requires_a_reference_date(
    banking_pack: Pack,
) -> None:
    with pytest.raises(ValueError, match="reference_date"):
        control.check(
            DISCLOSURE,
            [],
            ruleset=banking_pack,
            metadata=FULL_METADATA,
            reference_date=None,
        )


def test_an_iso_string_reference_date_is_accepted(banking_pack: Pack) -> None:
    result = control.check(
        DISCLOSURE,
        [],
        ruleset=banking_pack,
        metadata=FULL_METADATA,
        reference_date="2026-08-08",
    )
    assert result.decision in {Decision.CLEAR, Decision.ESCALATE}


def test_a_datetime_is_refused(banking_pack: Pack) -> None:
    with pytest.raises(TypeError, match="not a datetime"):
        control.check(
            DISCLOSURE,
            [],
            ruleset=banking_pack,
            metadata=FULL_METADATA,
            reference_date=datetime.datetime(2026, 8, 8, 12, 0),  # noqa: DTZ001
        )


def test_a_malformed_reference_date_is_refused(banking_pack: Pack) -> None:
    with pytest.raises(ValueError, match="ISO date"):
        control.check(
            DISCLOSURE,
            [],
            ruleset=banking_pack,
            metadata=FULL_METADATA,
            reference_date="8 August 2026",
        )


# ── The audit record ────────────────────────────────────────────────────────


def test_the_record_identifies_the_pack_by_hash(banking_pack: Pack) -> None:
    result = run(DISCLOSURE, [{"id": "a", "text": "x"}], ruleset=banking_pack)
    ruleset = audit_field(result.audit, "ruleset")
    assert ruleset["name"] == "eu-retail-banking"
    assert ruleset["version"] == "1.2.0"
    assert ruleset["content_sha256"] == banking_pack.content_sha256


def test_the_record_names_the_predicates_and_their_source_hashes(
    banking_pack: Pack,
) -> None:
    from groundlens.packs import predicates as predicates_module

    result = run(DISCLOSURE, [{"id": "a", "text": "x"}], ruleset=banking_pack)
    recorded = audit_field(result.audit, "predicates")
    by_name = {entry["name"]: entry["source_sha256"] for entry in recorded}
    assert set(by_name) == set(banking_pack.predicate_names())
    assert (
        by_name["banking.disclosure_present"]
        == predicates_module.entry("banking.disclosure_present").source_sha256
    )


def test_the_record_stores_metadata_keys_and_never_values(banking_pack: Pack) -> None:
    metadata = {"product_type": "mortgage", "disclosure_set": "SECRET-VALUE-42"}
    result = run(DISCLOSURE, [{"id": "a", "text": "x"}], ruleset=banking_pack, metadata=metadata)
    keys = audit_field(result.audit, "metadata_keys")
    assert keys == ["disclosure_set", "product_type"]
    assert "SECRET-VALUE-42" not in repr(result.audit)


def test_the_record_hashes_evidence_by_id(banking_pack: Pack) -> None:
    result = run(
        DISCLOSURE,
        [{"id": "b", "text": "two"}, {"id": "a", "text": "one"}],
        ruleset=banking_pack,
    )
    evidence = audit_field(result.audit, "evidence")
    assert [item["id"] for item in evidence] == ["a", "b"]
    assert evidence[0]["sha256"] == hashlib.sha256(b"one").hexdigest()


def test_the_record_counts_are_integers(banking_pack: Pack) -> None:
    answer = f"The payment is €999. {DISCLOSURE}"
    result = run(answer, [{"id": "a", "text": "nothing"}], ruleset=banking_pack)
    counts = audit_field(result.audit, "counts")
    assert set(counts) == {
        "facts_extracted",
        "facts_matched",
        "facts_unmatched",
        "facts_contradicted",
        "rules_evaluated",
        "rules_failed",
    }
    assert all(isinstance(value, int) and not isinstance(value, bool) for value in counts.values())
    assert counts["rules_evaluated"] == len(banking_pack.rules)
    assert counts["facts_unmatched"] == 1


def test_the_record_carries_no_float_anywhere(banking_pack: Pack) -> None:
    answer = f"The payment is €999. {DISCLOSURE}"
    result = run(answer, [{"id": "a", "text": "nothing"}], ruleset=banking_pack)
    seen: list[object] = []

    def walk(value: object) -> None:
        assert not isinstance(value, float), f"float in the audit record: {value!r}"
        if isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
        elif isinstance(value, list | tuple | set):
            for item in value:
                walk(item)

    for name in ("counts", "determinism", "ruleset", "evidence", "predicates"):
        if hasattr(result.audit, name):
            seen.append(getattr(result.audit, name))
            walk(getattr(result.audit, name))
    assert seen


def test_the_record_states_the_determinism_settings(banking_pack: Pack) -> None:
    result = run(DISCLOSURE, [{"id": "a", "text": "x"}], ruleset=banking_pack)
    determinism = audit_field(result.audit, "determinism")
    assert determinism["unicode_form"] == "NFKC"
    assert determinism["locale_profile"] == "eu-es"
    assert determinism["reference_date"] == "2026-08-08"


# ── Pack resolution ─────────────────────────────────────────────────────────


def test_a_pack_name_resolves(banking_pack: Pack) -> None:
    result = run(DISCLOSURE, [{"id": "a", "text": "x"}], ruleset="eu-retail-banking")
    assert audit_field(result.audit, "ruleset")["content_sha256"] == (banking_pack.content_sha256)


def test_a_pack_path_resolves(banking_pack: Pack, tmp_path: Path) -> None:
    copied = tmp_path / "pack.yaml"
    copied.write_bytes(banking_pack.source_path.read_bytes())
    result = run(DISCLOSURE, [{"id": "a", "text": "x"}], ruleset=copied)
    assert audit_field(result.audit, "ruleset")["content_sha256"] == (banking_pack.content_sha256)


def test_a_nonsense_ruleset_is_refused() -> None:
    with pytest.raises(TypeError, match="ruleset must be"):
        run(DISCLOSURE, [], ruleset=42)


def test_the_decision_rationale_pack_runs_end_to_end() -> None:
    metadata = {
        "context_quality_validated": True,
        "consistency_check_passed": True,
        "audit_logged": True,
        "injection_test_passed": True,
    }
    answer = (
        "The counterparty risk score is 42, therefore the case is deferred. "
        "Documentation is missing, so we cannot determine the outcome. See [policy#p1]."
    )
    result = control.check(
        answer,
        [{"id": "policy#p1", "text": "Risk score 42 recorded for this counterparty."}],
        ruleset="decision-rationale",
        metadata=metadata,
    )
    assert result.decision is Decision.CLEAR

    without_screening = control.check(
        answer,
        [{"id": "policy#p1", "text": "Risk score 42 recorded for this counterparty."}],
        ruleset="decision-rationale",
        metadata={},
    )
    assert without_screening.decision is Decision.ESCALATE
    assert sum(1 for f in without_screening.findings if f.code == "pack.metadata.missing") == 4
