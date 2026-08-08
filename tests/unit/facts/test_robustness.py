"""Adversarial input.

The extractor reads model output, which is untrusted. A regex that backtracks
quadratically is a denial-of-service bug, not a style issue, so the pathological
shapes are pinned with a time budget.
"""

from __future__ import annotations

import time
from datetime import date

import pytest

from .conftest import make_profile

REF = date(2026, 2, 10)
BUDGET_SECONDS = 3.0


@pytest.fixture(scope="module")
def gb():
    return make_profile(
        "en-gb", decimal_separator=".", group_separator=",", date_order="DMY", currency="GBP"
    )


PATHOLOGICAL = {
    "digit_group_run": "1" + ",000" * 2000,
    "comma_run": "1" + ",1" * 5000,
    "duration_chain": "30 days and " * 300 + "30 days",
    "within_chain": "within " + "30 days and " * 200 + "30 days",
    "modal_run": "must " * 2000,
    "no_subject_modal": "no " + "word " * 300 + "may act",
    "whitespace": " " * 20000 + "must do it",
    "dots": "." * 20000,
    "brackets": "[" * 5000 + "3" + "]" * 5000,
    "citation_chain": "Article " + "1." * 500,
    "currency_run": "EUR 1 " * 2000,
    "percent_run": "1% " * 2000,
    "nested_parens": "(" * 2000 + "1" + ")" * 2000,
    "mixed": ("must not, if 1.000,00 EUR within 30 days, Article 12 " * 100),
}


@pytest.mark.parametrize("name", sorted(PATHOLOGICAL))
def test_pathological_input_stays_within_budget(gb, name):
    from groundlens.facts import extract_facts

    text = PATHOLOGICAL[name]
    start = time.perf_counter()
    facts = extract_facts(text, locale=gb, reference_date=REF)
    elapsed = time.perf_counter() - start
    assert elapsed < BUDGET_SECONDS, f"{name} took {elapsed:.2f}s"
    for fact in facts:
        assert fact.raw == text[fact.span[0] : fact.span[1]]


@pytest.mark.parametrize("name", sorted(PATHOLOGICAL))
def test_pathological_input_is_still_deterministic(gb, name):
    from groundlens.facts import extract_facts

    text = PATHOLOGICAL[name]
    first = extract_facts(text, locale=gb, reference_date=REF)
    assert extract_facts(text, locale=gb, reference_date=REF) == first


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "\n\n\n",
        "must",
        "must ",
        ".",
        "€",
        "%",
        "[]",
        "§",
        "1,",
        ",1",
        "within",
        "no later than",
        "if",
        "\u0000",
        "🙂 must 🙂 not 🙂 disclose",
    ],
)
def test_degenerate_input_does_not_raise(gb, text):
    from groundlens.facts import extract_facts

    facts = extract_facts(text, locale=gb, reference_date=REF)
    for fact in facts:
        assert fact.raw == text[fact.span[0] : fact.span[1]]


def test_the_fact_cap_holds_on_a_dense_document(gb):
    from groundlens.facts import ExtractConfig, extract_facts

    text = "The fee is 1 EUR. " * 5000
    facts = extract_facts(text, locale=gb, reference_date=REF, config=ExtractConfig(max_facts=100))
    assert len(facts) == 100


def test_matching_a_dense_answer_against_dense_evidence(gb):
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    answer = "The fee is 1,250.50 EUR. " * 40
    evidence = [Evidence(id=f"doc#{n}", text="The fee is 1,300.00 EUR. " * 40) for n in range(5)]
    facts = extract_facts(answer, locale=gb, reference_date=REF)
    start = time.perf_counter()
    matches = match_facts(facts, evidence, locale=gb, config=MatchConfig(reference_date=REF))
    assert time.perf_counter() - start < 10.0
    assert len(matches) == len(facts)
    assert {m.state.value for m in matches} == {"contradicted"}
