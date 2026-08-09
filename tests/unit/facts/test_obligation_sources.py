"""Obligations attributed to a source rather than carried by a modal.

Evidence is written "the policy requires that you notify us" far more often
than answers are. Without these cues the evidence carries no obligation at all,
the answer's faithful restatement has nothing to match against, and it reads
UNMATCHED — a fail on a correct answer, which is the most expensive thing this
library can do.

Every positive form below has its negation tested next to it. A negation pass
layered over a positive cue is exactly how an extractor comes to report a duty
where the source states an exemption, so the negations are single lexical
entries and these tests are what hold them there.
"""

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


def polarities(text, profile):
    from groundlens.facts import extract_facts

    return [
        fact.normalised
        for fact in extract_facts(text, locale=profile, reference_date=REF)
        if fact.kind.value == "obligation"
    ]


def forms(text, profile):
    from groundlens.facts import extract_facts

    return [
        dict(fact.attrs)["operator_form"]
        for fact in extract_facts(text, locale=profile, reference_date=REF)
        if fact.kind.value == "obligation"
    ]


# ---------------------------------------------------------------------------
# English
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The policy requires that you notify us of any change.",
        "The rules require that the firm notify the customer.",
        "It is required that the firm notify the customer.",
        "The guidance mandates that the report be filed.",
        "The policy requires the customer to notify us.",
        "The regulation requires you to keep the records.",
        "The directive obliges the firm to publish the fee.",
    ],
)
def test_a_source_framed_duty_is_an_obligation(gb, text):
    assert polarities(text, gb) == ["must"]


@pytest.mark.parametrize(
    "text",
    [
        "The policy does not require that you notify us.",
        "The rules do not require that the firm notify the customer.",
        "The directive does not oblige the firm to publish the fee.",
    ],
)
def test_the_negation_is_an_exemption_and_never_a_duty(gb, text):
    assert polarities(text, gb) == ["need_not"]


def test_the_existing_passive_form_is_untouched(gb):
    assert forms("The firm is required to notify the customer.", gb) == ["required_to"]
    assert polarities("The firm is not required to notify the customer.", gb) == ["need_not"]


def test_it_is_mandatory_that_was_already_covered(gb):
    """Named in the brief as a sibling; the lexicon already had it.

    Asserted here so a later reader does not add a second entry for it.
    """
    assert forms("It is mandatory that the firm notify the customer.", gb) == ["mandatory"]


# ---------------------------------------------------------------------------
# English: what "requires" must not swallow
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The process requires two days to complete.",
        "The migration requires 30 days to finish.",
        "The review requires more time to conclude.",
    ],
)
def test_requires_a_quantity_to_do_something_is_a_measurement_not_a_duty(gb, text):
    """ "requires X to Y" has the shape of a duty and often is not one.

    The object is restricted to a determiner-headed noun phrase for exactly
    this reason: "two days" and "more time" do not open one.
    """
    assert polarities(text, gb) == []


def test_a_bare_requires_with_no_complement_is_not_an_obligation(gb):
    assert polarities("The application requires a licence.", gb) == []


# ---------------------------------------------------------------------------
# Spanish
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "La política exige que el cliente lo comunique.",
        "Las normas exigen que la entidad informe al cliente.",
        "El reglamento requiere que se conserven los registros.",
        "La directiva obliga a la entidad a publicar la comisión.",
    ],
)
def test_spanish_source_framed_duty_is_an_obligation(eu, text):
    assert polarities(text, eu) == ["must"]


@pytest.mark.parametrize(
    "text",
    [
        "La política no exige que el cliente lo comunique.",
        "El reglamento no requiere que se conserven los registros.",
        "La directiva no obliga a la entidad a publicar la comisión.",
    ],
)
def test_spanish_negations_are_exemptions(eu, text):
    assert polarities(text, eu) == ["need_not"]


# ---------------------------------------------------------------------------
# the reason the cues were added at all
# ---------------------------------------------------------------------------


def test_a_grounded_restatement_of_a_requires_that_source_matches(gb):
    """The false alarm this change exists to remove.

    The source frames the duty on an instrument; the answer restates it with a
    modal. Same duty, same strength, so the answer must read MATCHED rather
    than "and no source says that".
    """
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    answer = "The amounts quoted to you have to match the ones in the product documentation."
    facts = [
        fact
        for fact in extract_facts(answer, locale=gb, reference_date=REF)
        if fact.kind.value == "obligation"
    ]
    matches = match_facts(
        facts,
        [
            Evidence(
                id="doc-1#p0",
                text=(
                    "The guideline requires that any monetary amount communicated to a "
                    "customer corresponds to the amount in the product documentation."
                ),
            )
        ],
        locale=gb,
        config=MatchConfig(reference_date=REF),
    )
    assert [m.state.value for m in matches] == ["matched"]


def test_a_strengthened_restatement_still_contradicts(gb):
    """The cue must not turn every obligation into agreement."""
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    facts = [
        fact
        for fact in extract_facts(
            "You must notify us of any change.", locale=gb, reference_date=REF
        )
        if fact.kind.value == "obligation"
    ]
    matches = match_facts(
        facts,
        [
            Evidence(
                id="doc-1#p0",
                text="The policy does not require that you notify us of a change.",
            )
        ],
        locale=gb,
        config=MatchConfig(reference_date=REF),
    )
    assert [m.state.value for m in matches] == ["contradicted"]
