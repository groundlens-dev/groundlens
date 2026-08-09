"""Extractor behaviour that the YAML corpus cannot express."""

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


def run(text, profile, **kwargs):
    from groundlens.facts import extract_facts

    return extract_facts(text, locale=profile, reference_date=REF, **kwargs)


def kinds(facts):
    return [f.kind.value for f in facts]


# ---------------------------------------------------------------------------
# spans and ordering
# ---------------------------------------------------------------------------


def test_empty_text(gb):
    assert run("", gb) == ()


def test_facts_are_in_document_order(gb):
    facts = run("Pay 100 EUR by 3 March 2026 under Article 12.", gb)
    starts = [f.span[0] for f in facts]
    assert starts == sorted(starts)


def test_raw_always_slices_back_out_of_the_text(gb):
    text = "The firm must pay 1,250.50 EUR within 30 days under Article 12(3)."
    for fact in run(text, gb):
        assert fact.raw == text[fact.span[0] : fact.span[1]]


def test_the_extractor_does_not_normalise_again(gb):
    """A pre-composed character must keep the caller's offsets."""
    # The caller has already run NFKC; a raw NBSP here would have become a
    # plain space upstream, so offsets must be taken as given.
    text = "The fee is 100 EUR today."
    facts = run(text, gb)
    assert facts
    for fact in facts:
        assert fact.raw == text[fact.span[0] : fact.span[1]]


def test_only_the_eight_contract_kinds_are_emitted(gb):
    text = (
        "The firm must pay 1,250.50 EUR (a rise of 2%) within 30 days, no later than "
        "3 March 2026, under Article 12 and 47 other rules."
    )
    allowed = {
        "number",
        "currency",
        "percent",
        "date",
        "duration",
        "deadline",
        "citation",
        "obligation",
    }
    assert set(kinds(run(text, gb))) <= allowed


# ---------------------------------------------------------------------------
# overlap suppression
# ---------------------------------------------------------------------------


def test_a_currency_swallows_its_number(gb):
    facts = run("The fee is 1,250.50 EUR.", gb)
    assert kinds(facts) == ["currency"]


def test_a_deadline_swallows_its_duration(gb):
    facts = run("Reply within 30 days.", gb)
    assert kinds(facts) == ["deadline"]


def test_a_citation_swallows_its_number(gb):
    facts = run("See Article 12.", gb)
    assert kinds(facts) == ["citation"]


def test_a_percent_swallows_its_number(gb):
    facts = run("The rate is 12.5%.", gb)
    assert kinds(facts) == ["percent"]


def test_a_bare_number_still_surfaces(gb):
    facts = run("There are 47 branches.", gb)
    assert kinds(facts) == ["number"]


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def test_max_facts_truncates_deterministically(gb):
    from groundlens.facts import ExtractConfig

    text = " ".join(f"item {n}" for n in range(50))
    facts = run(text, gb, config=ExtractConfig(max_facts=5))
    assert len(facts) == 5
    assert facts == run(text, gb, config=ExtractConfig(max_facts=5))
    assert [f.span[0] for f in facts] == sorted(f.span[0] for f in facts)


def test_kinds_filter(gb):
    from groundlens.facts import ExtractConfig

    text = "The firm must pay 100 EUR."
    facts = run(text, gb, config=ExtractConfig(kinds=frozenset({"obligation"})))
    assert kinds(facts) == ["obligation"]


def test_weak_cues_can_be_switched_off(gb):
    from groundlens.facts import ExtractConfig

    text = "You can request a copy."
    assert kinds(run(text, gb)) == ["obligation"]
    assert run(text, gb, config=ExtractConfig(weak_cues=False)) == ()


def test_config_accepts_a_rule_pack_mapping(gb):
    facts = run("You can request a copy.", gb, config={"weak_cues": False})
    assert facts == ()


def test_unknown_config_keys_are_ignored(gb):
    facts = run("The fee is 100 EUR.", gb, config={"invented_key_from_the_future": 3})
    assert kinds(facts) == ["currency"]


# ---------------------------------------------------------------------------
# obligation clause and attributes
# ---------------------------------------------------------------------------


def obligations(text, profile):
    return [f for f in run(text, profile) if f.kind.value == "obligation"]


def test_operator_span_points_at_the_operator(gb):
    text = "The firm must not disclose the records."
    fact = obligations(text, gb)[0]
    start, end = (int(part) for part in dict(fact.attrs)["operator_span"].split(":"))
    assert text[start:end] == "must not"


def test_governed_span_is_the_clause_after_the_operator(gb):
    text = "The firm must not disclose the records."
    fact = obligations(text, gb)[0]
    start, end = (int(part) for part in dict(fact.attrs)["governed_span"].split(":"))
    assert text[start:end].strip() == "disclose the records"


def test_condition_span_slices_back_out(gb):
    text = "If the account is closed, the firm must notify the customer."
    fact = obligations(text, gb)[0]
    attrs = dict(fact.attrs)
    start, end = (int(part) for part in attrs["condition_span"].split(":"))
    assert text[start:end] == attrs["condition"]


def test_subject_text_is_recorded_but_is_not_a_matchable_field(gb):
    text = "Acme Financial Services Ltd must retain the records."
    fact = obligations(text, gb)[0]
    attrs = dict(fact.attrs)
    assert attrs["subject_text"] == "Acme Financial Services Ltd"
    # No actor/entity kind exists, deliberately.
    assert all(f.kind.value != "actor" for f in run(text, gb))


def test_predicate_key_drops_stopwords_and_is_sorted(gb):
    fact = obligations("The firm must retain the client records.", gb)[0]
    key = dict(fact.attrs)["predicate_key"]
    assert key == " ".join(sorted(key.split()))
    assert "the" not in key.split()
    assert "records" in key.split()


def test_one_obligation_per_operator(gb):
    text = "The firm must retain the records, and the firm may not disclose them."
    assert len(obligations(text, gb)) == 2


def test_a_bare_modal_with_no_clause_is_dropped(gb):
    assert obligations("Must.", gb) == []


def test_month_named_may_is_not_a_permission(gb):
    text = "The report covers 3 May 2026."
    assert obligations(text, gb) == []


# ---------------------------------------------------------------------------
# deadlines never touch the clock
# ---------------------------------------------------------------------------


def test_relative_deadlines_use_the_passed_reference_date(gb):
    from groundlens.facts import extract_facts

    early = extract_facts("Reply within 30 days.", locale=gb, reference_date=date(2020, 1, 1))
    late = extract_facts("Reply within 30 days.", locale=gb, reference_date=date(2030, 1, 1))
    assert early[0].normalised == "2020-01-31"
    assert late[0].normalised == "2030-01-31"


def test_business_day_deadlines_are_not_invented(gb):
    fact = run("Reply within 10 business days.", gb)[0]
    attrs = dict(fact.attrs)
    assert attrs["unresolved_reason"] == "business_days"
    assert "due_date" not in attrs


def test_event_anchored_deadlines_are_not_invented(gb):
    fact = run("Reply within 30 days of receipt.", gb)[0]
    attrs = dict(fact.attrs)
    assert attrs["anchor"] == "event"
    assert "due_date" not in attrs
    assert fact.normalised == "P30D"
