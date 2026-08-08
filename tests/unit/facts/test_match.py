"""Matcher behaviour, with the emphasis on contradiction detection."""

from __future__ import annotations

from datetime import date

import pytest

from .conftest import make_profile

REF = date(2026, 2, 10)


@pytest.fixture(scope="module")
def gb():
    return make_profile(
        "en-gb", decimal_separator=".", group_separator=",", date_order="DMY", currency="GBP"
    )


@pytest.fixture(scope="module")
def eu():
    return make_profile(
        "eu-es", decimal_separator=",", group_separator=".", date_order="DMY", currency="EUR"
    )


def check(answer, evidence_texts, profile, **config):
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    facts = extract_facts(answer, locale=profile, reference_date=REF)
    evidence = [
        Evidence(id=f"doc-1#p{index}", text=text) for index, text in enumerate(evidence_texts)
    ]
    matches = match_facts(
        facts,
        evidence,
        locale=profile,
        config=MatchConfig(reference_date=REF, **config),
    )
    return {m.fact.kind.value: m for m in matches}, matches


def state(matches, kind):
    return matches[kind].state.value


# ---------------------------------------------------------------------------
# basics
# ---------------------------------------------------------------------------


def test_one_match_per_fact_in_input_order(gb):
    from groundlens.facts import extract_facts, match_facts

    facts = extract_facts("Pay 100 EUR by 3 March 2026.", locale=gb, reference_date=REF)
    matches = match_facts(facts, [], locale=gb)
    assert len(matches) == len(facts)
    assert [m.fact for m in matches] == list(facts)


def test_no_evidence_means_unmatched(gb):
    by_kind, _ = check("The fee is 100 EUR.", [], gb)
    assert state(by_kind, "currency") == "unmatched"


def test_empty_evidence_item_means_unmatched(gb):
    by_kind, _ = check("The fee is 100 EUR.", [""], gb)
    assert state(by_kind, "currency") == "unmatched"


def test_no_facts_means_no_matches(gb):
    from groundlens.facts import match_facts

    assert match_facts([], [], locale=gb) == ()


# ---------------------------------------------------------------------------
# MATCHED always carries a span
# ---------------------------------------------------------------------------


def test_a_match_names_an_evidence_id_and_a_span(gb):
    evidence = "The arrangement fee is 1,250.50 EUR for retail clients."
    by_kind, _ = check("The arrangement fee is 1,250.50 EUR.", [evidence], gb)
    match = by_kind["currency"]
    assert match.state.value == "matched"
    assert match.evidence_id == "doc-1#p0"
    start, end = match.evidence_span
    assert evidence[start:end] == "1,250.50 EUR"


def test_no_match_is_ever_emitted_without_a_span(gb):
    long_evidence = ("filler text " * 400) + "The fee is 1,250.50 EUR."
    _, matches = check("The fee is 1,250.50 EUR.", [long_evidence], gb)
    for match in matches:
        if match.state.value in {"matched", "contradicted"}:
            assert match.evidence_span is not None
            assert match.evidence_id is not None


def test_a_reformatted_value_still_matches(eu):
    by_kind, _ = check("El importe es de 1.000 EUR.", ["El importe es 1 000,00 EUR."], eu)
    assert state(by_kind, "currency") == "matched"


# ---------------------------------------------------------------------------
# CONTRADICTED
# ---------------------------------------------------------------------------


def test_a_wrong_number_in_a_right_sentence_is_contradicted(gb):
    evidence = "The arrangement fee is 1,250.50 EUR for retail clients."
    by_kind, _ = check("The arrangement fee is 1,300.00 EUR.", [evidence], gb)
    match = by_kind["currency"]
    assert match.state.value == "contradicted"
    assert match.evidence_value == "EUR 1250.5"
    assert match.evidence_span is not None


def test_an_unrelated_number_elsewhere_is_not_a_contradiction(gb):
    evidence = "Our head office employs 1,300 people in seventeen countries."
    by_kind, _ = check("The arrangement fee is 1,250.50 EUR.", [evidence], gb)
    assert state(by_kind, "currency") == "unmatched"


def test_a_different_currency_is_not_silently_matched(gb):
    by_kind, _ = check("The fee is 1,000 USD.", ["The fee is 1,000 EUR."], gb)
    assert state(by_kind, "currency") == "contradicted"


def test_a_wrong_date_is_contradicted(gb):
    by_kind, _ = check(
        "The report was filed on 4 March 2026.",
        ["The report was filed on 3 March 2026."],
        gb,
    )
    assert by_kind["date"].state.value == "contradicted"
    assert by_kind["date"].evidence_value == "2026-03-03"


def test_a_wrong_article_number_is_contradicted(gb):
    by_kind, _ = check(
        "Reports are due under Article 13.", ["Reports are due under Article 12."], gb
    )
    assert by_kind["citation"].state.value == "contradicted"
    assert by_kind["citation"].evidence_value == "ARTICLE 12"


def test_a_different_instrument_is_not_a_contradiction(gb):
    by_kind, _ = check(
        "Reports are due under Article 12.", ["Reports are due under Annex II."], gb
    )
    assert by_kind["citation"].state.value == "unmatched"


def test_business_days_do_not_match_plain_days(gb):
    by_kind, _ = check("Retention lasts 30 days.", ["Retention lasts 30 business days."], gb)
    match = by_kind["duration"]
    assert match.state.value == "contradicted"
    assert "business days" in match.evidence_value


def test_the_context_gate_can_be_disabled_explicitly(gb):
    evidence = "Our head office employs 1,300 people."
    by_kind, _ = check(
        "The arrangement fee is 1,250.50 EUR.",
        [evidence],
        gb,
        contradiction_requires_context=False,
    )
    assert state(by_kind, "currency") == "unmatched"  # different currency unit


# ---------------------------------------------------------------------------
# tolerances
# ---------------------------------------------------------------------------


def test_tolerance_is_exact_by_default(gb):
    by_kind, _ = check("The rate is 12.5%.", ["The rate is 12.6%."], gb)
    assert state(by_kind, "percent") == "contradicted"


def test_absolute_tolerance_from_a_decimal_string(gb):
    by_kind, _ = check(
        "The rate is 12.5%.", ["The rate is 12.6%."], gb, tolerances={"percent": "0.2"}
    )
    assert state(by_kind, "percent") == "matched"


def test_relative_tolerance_from_a_decimal_string(gb):
    by_kind, _ = check(
        "The fee is 1,000.00 EUR.",
        ["The fee is 1,005.00 EUR."],
        gb,
        relative_tolerances={"currency": "0.01"},
    )
    assert state(by_kind, "currency") == "matched"


def test_tolerances_are_parsed_from_a_rule_pack_mapping(gb):
    from groundlens.facts import MatchConfig

    config = MatchConfig.coerce({"percent": {"tolerance": "0.2"}}, reference_date=REF)
    assert str(config.tolerance_for("percent")) == "0.2"
    assert str(config.tolerance_for("currency")) == "0"


def test_a_bad_tolerance_string_does_not_crash(gb):
    from groundlens.facts import MatchConfig

    config = MatchConfig.coerce({"percent": {"tolerance": "not a number"}})
    assert str(config.tolerance_for("percent")) == "0"


# ---------------------------------------------------------------------------
# obligation polarity — the highest-value check
# ---------------------------------------------------------------------------


def obligation(answer, evidence, profile, **config):
    by_kind, _ = check(answer, evidence, profile, **config)
    return by_kind["obligation"]


def test_must_where_the_evidence_says_may_is_contradicted(gb):
    match = obligation(
        "The firm must retain the records.", ["The firm may retain the records."], gb
    )
    assert match.state.value == "contradicted"
    assert match.evidence_value.startswith("may")


def test_must_where_the_evidence_says_must_not_is_contradicted(gb):
    match = obligation(
        "The firm must disclose the records.",
        ["The firm must not disclose the records."],
        gb,
    )
    assert match.state.value == "contradicted"
    assert match.evidence_value.startswith("must_not")


def test_must_not_where_the_evidence_says_need_not_is_contradicted(gb):
    match = obligation(
        "The firm must not retain the records.",
        ["The firm need not retain the records."],
        gb,
    )
    assert match.state.value == "contradicted"


def test_should_where_the_evidence_says_must_is_contradicted(gb):
    match = obligation(
        "The firm should retain the records.", ["The firm must retain the records."], gb
    )
    assert match.state.value == "contradicted"


def test_negative_recommendation_contradicts_the_positive_one(gb):
    match = obligation(
        "The firm should publish the note.", ["The firm should not publish the note."], gb
    )
    assert match.state.value == "contradicted"
    assert match.evidence_value.startswith("should:negative")


def test_same_polarity_different_wording_matches(gb):
    match = obligation(
        "The firm must retain the records.",
        ["The firm is required to retain the records."],
        gb,
    )
    assert match.state.value == "matched"


def test_polarity_across_languages(eu):
    match = obligation(
        "La entidad debe conservar los registros.",
        ["La entidad no debe conservar los registros."],
        eu,
    )
    assert match.state.value == "contradicted"


def test_an_unrelated_obligation_is_not_a_contradiction(gb):
    match = obligation(
        "The firm must retain the records.",
        ["The customer may cancel the direct debit at any time."],
        gb,
    )
    assert match.state.value == "unmatched"


def test_dropping_a_condition_is_flagged_rather_than_passed(gb):
    match = obligation(
        "The firm must notify the customer.",
        ["If the account is closed, the firm must notify the customer."],
        gb,
    )
    assert match.state.value == "uncheckable"


def test_keeping_the_condition_matches(gb):
    match = obligation(
        "If the account is closed, the firm must notify the customer.",
        ["If the account is closed, the firm must notify the customer."],
        gb,
    )
    assert match.state.value == "matched"


def test_conditional_check_can_be_switched_off(gb):
    match = obligation(
        "The firm must notify the customer.",
        ["If the account is closed, the firm must notify the customer."],
        gb,
        conditional_mismatch_uncheckable=False,
    )
    assert match.state.value == "matched"


# ---------------------------------------------------------------------------
# UNCHECKABLE
# ---------------------------------------------------------------------------


def test_an_ambiguous_currency_symbol_is_uncheckable_not_wrong(eu):
    by_kind, _ = check("The penalty is $500.", ["The penalty is 500 EUR."], eu)
    assert state(by_kind, "currency") == "uncheckable"


def test_a_scope_hedged_obligation_is_uncheckable(gb):
    match = obligation(
        "Nothing in this Article shall prevent the firm from charging a fee.",
        ["The firm may charge a fee."],
        gb,
    )
    assert match.state.value == "uncheckable"


def test_a_separator_ambiguity_downgrades_a_contradiction(eu):
    """A difference that may be our reading of the separators, not the author's error."""
    by_kind, _ = check("El importe es de 1,000 EUR.", ["El importe es de 999 EUR."], eu)
    assert state(by_kind, "currency") == "uncheckable"


def test_an_ambiguous_date_still_matches_when_the_evidence_agrees(gb):
    by_kind, _ = check("Filed on 03/04/2026.", ["Filed on 3 April 2026."], gb)
    assert by_kind["date"].state.value == "matched"


# ---------------------------------------------------------------------------
# reference date
# ---------------------------------------------------------------------------


def test_relative_deadlines_in_evidence_use_the_same_anchor(gb):
    by_kind, _ = check("Reply within 30 days.", ["You must reply within 30 days."], gb)
    assert state(by_kind, "deadline") == "matched"


def test_a_deadline_without_a_reference_date_is_refused_not_guessed(gb):
    from groundlens.facts import extract_facts, match_facts
    from groundlens.types import Evidence

    facts = extract_facts("Reply within 30 days.", locale=gb, reference_date=REF)
    stripped = [
        type(f)(
            kind=f.kind,
            raw=f.raw,
            span=f.span,
            normalised=f.normalised,
            attrs=tuple((k, v) for k, v in f.attrs if k != "reference_date"),
        )
        for f in facts
    ]
    with pytest.raises(ValueError, match="reference_date"):
        match_facts(stripped, [Evidence(id="e", text="x")], locale=gb)


def test_evidence_is_indexed_in_a_stable_order(gb):
    answer = "The fee is 100 EUR."
    forward = check(answer, ["The fee is 100 EUR.", "The fee is 100 EUR."], gb)[1]
    backward = check(answer, ["The fee is 100 EUR.", "The fee is 100 EUR."], gb)[1]
    assert forward == backward
