"""A DEADLINE decided against a DATE, on the resolved due day.

A source states the day a period ends; an answer states the day the reader has
to act by. They are written differently, they land in different kinds, and a
same-kind-only matcher can never put them next to each other — which made
``fact.contradicted.deadline`` unreachable for every paraphrased deadline.

The crossing is deliberately narrow: DEADLINE against DATE and nothing else,
compared on the resolved ISO day and never on the surface text.
"""

from __future__ import annotations

from datetime import date

import pytest

from .conftest import make_profile

REF = date(2026, 8, 8)


@pytest.fixture(scope="module")
def gb():
    return make_profile(
        "en-gb", decimal_separator=".", group_separator=",", date_order="DMY", currency="GBP"
    )


def check(answer, evidence_texts, profile, reference_date=REF, **config):
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    facts = extract_facts(answer, locale=profile, reference_date=reference_date)
    evidence = [
        Evidence(id=f"doc-1#p{index}", text=text) for index, text in enumerate(evidence_texts)
    ]
    matches = match_facts(
        facts,
        evidence,
        locale=profile,
        config=MatchConfig(reference_date=reference_date, **config),
    )
    return {m.fact.kind.value: m for m in matches}


# ---------------------------------------------------------------------------
# the crossing
# ---------------------------------------------------------------------------


def test_a_deadline_contradicts_a_date_that_resolves_to_a_different_day(gb):
    by_kind = check(
        "You need to tell us by 2026-08-31 at the latest.",
        ["For agreements dated 2026-08-08 the period ends on 2026-08-22."],
        gb,
    )
    match = by_kind["deadline"]
    assert match.state.value == "contradicted"
    assert match.evidence_value == "2026-08-22"
    assert match.evidence_id == "doc-1#p0"
    assert match.evidence_span is not None


def test_a_deadline_matches_a_date_that_resolves_to_the_same_day(gb):
    by_kind = check(
        "You need to tell us by 2026-08-22 at the latest.",
        ["For agreements dated 2026-08-08 the period ends on 2026-08-22."],
        gb,
    )
    assert by_kind["deadline"].state.value == "matched"


def test_a_relative_deadline_is_compared_on_the_day_it_resolves_to(gb):
    """ "within 14 days" against a bare date: the resolution is the comparison."""
    by_kind = check(
        "You must respond within 14 days.",
        ["The response is due on 2026-09-30."],
        gb,
    )
    assert by_kind["deadline"].state.value == "contradicted"
    assert by_kind["deadline"].evidence_value == "2026-09-30"


def test_the_surface_text_is_not_what_is_compared(gb):
    """Two spellings of one day agree; a same-string test would not say so."""
    by_kind = check(
        "You must respond within 14 days.",
        ["The response is due on 22 August 2026."],
        gb,
    )
    assert by_kind["deadline"].state.value == "matched"


def test_no_dates_in_the_evidence_leaves_the_deadline_unmatched(gb):
    by_kind = check(
        "You need to tell us by 2026-08-31 at the latest.",
        ["The customer may withdraw from the agreement."],
        gb,
    )
    assert by_kind["deadline"].state.value == "unmatched"


# ---------------------------------------------------------------------------
# what the crossing must not do
# ---------------------------------------------------------------------------


def test_the_crossing_runs_one_way_only(gb):
    """A DATE in the answer is not decided against a DEADLINE in the evidence.

    A source's deadline is a duty; an answer's bare date may be anything at all
    ("the agreement was signed on ..."). Reading one as the other would invent
    contradictions on clean traffic, so the crossing is not symmetric.
    """
    by_kind = check(
        "The agreement was signed on 2026-01-05.",
        ["You must respond by 2026-08-22."],
        gb,
    )
    assert by_kind["date"].state.value == "unmatched"


def test_a_deadline_that_never_resolved_is_uncheckable_not_contradicted(gb):
    """Business days need a holiday calendar this library does not have.

    The deadline is relative and stays unresolved, so it is not compared
    against any date. "No source says this" would be a claim about the
    evidence; the truth is that the comparison could not be made.
    """
    by_kind = check(
        "You must respond within 14 business days.",
        ["The response is due on 2026-09-30."],
        gb,
    )
    assert by_kind["deadline"].state.value == "uncheckable"


def test_a_partial_date_cannot_contradict_a_full_one(gb):
    """A day that is only partly known is not evidence about a day that is.

    ``--08-31`` and ``2026-08-22`` differ as strings and say nothing about each
    other as days.
    """
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    facts = extract_facts("Tell us by 31 August.", locale=gb, reference_date=None)
    deadlines = [f for f in facts if f.kind.value == "deadline"]
    assert deadlines, "expected a deadline with no year"
    assert dict(deadlines[0].attrs)["due_date"].startswith("--")

    matches = match_facts(
        deadlines,
        [Evidence(id="doc-1#p0", text="The period ends on 2026-08-22.")],
        locale=gb,
        config=MatchConfig(reference_date=REF),
    )
    assert matches[0].state.value != "contradicted"


def test_two_deadlines_still_compare_as_deadlines(gb):
    by_kind = check(
        "You must respond by 2026-08-31.",
        ["You must respond by 2026-08-22."],
        gb,
    )
    assert by_kind["deadline"].state.value == "contradicted"


def test_an_event_anchored_deadline_is_still_compared_as_a_duration(gb):
    """ "within 30 days of receipt" hangs off a day nobody can name.

    It is unresolved as a date and must not be reported as uncheckable on that
    account: the duration is comparable and is what the matcher uses.
    """
    by_kind = check(
        "You must respond within 30 days of receipt.",
        ["The customer must respond within 60 days of receipt."],
        gb,
    )
    assert by_kind["deadline"].state.value == "contradicted"
