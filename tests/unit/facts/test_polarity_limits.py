"""The polarity extractor's known limits, pinned as tests.

These are not aspirational.  Each one records what the extractor does *today*
on a construction it gets wrong or gives up on, so that a change in behaviour
shows up as a failing test rather than as a silent change in what a reviewer is
told.  If you fix one of these, change the assertion in the same commit.

Two categories:

``test_known_false_positive_*``
    The extractor reports an obligation where a lawyer would say there is none,
    or reports the wrong strength.  These inflate the escalation rate.

``test_known_false_negative_*``
    The extractor stays silent where there is a real obligation.  These lower
    recall.  Silence is the better failure of the two — an inverted polarity is
    worse than a missed one — and the design prefers it wherever the two trade
    off.
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


def polarities(text, profile):
    from groundlens.facts import extract_facts

    return [
        (fact.normalised, dict(fact.attrs).get("scope_uncertain", ""))
        for fact in extract_facts(text, locale=profile, reference_date=REF)
        if fact.kind.value == "obligation"
    ]


# ---------------------------------------------------------------------------
# False positives
# ---------------------------------------------------------------------------


def test_known_false_positive_epistemic_may(gb):
    """ "may" meaning "possibly" is read as a permission.

    The single largest false-positive source in ordinary prose.  A pack running
    over customer-facing narrative should expect it; a pack over regulatory text
    largely will not see it.
    """
    assert polarities("The delay may cause the payment to fail.", gb) == [("may", "")]


def test_known_false_positive_ability_can(gb):
    """ "can" meaning capability is read as a permission, flagged only as weak."""
    from groundlens.facts import ExtractConfig, extract_facts

    text = "This can lead to a penalty."
    assert polarities(text, gb) == [("may", "")]
    off = extract_facts(text, locale=gb, reference_date=REF, config=ExtractConfig(weak_cues=False))
    assert off == ()


def test_known_false_positive_reported_speech(gb):
    """An obligation attributed to a third party is reported as an obligation."""
    assert polarities("The firm said it must file the report.", gb) == [("must", "")]


def test_known_false_positive_quoted_material(gb):
    """Quotation marks are not tracked, so a quoted duty is reported as stated."""
    text = 'The complaint said: "The firm must file the report."'
    assert ("must", "") in polarities(text, gb)


def test_known_false_positive_shall_as_future_tense(gb):
    """Legal-drafting "shall" and future-tense "shall" are not distinguished."""
    assert polarities("We shall write to you next week.", gb) == [("must", "")]


def test_known_false_positive_only_x_may(gb):
    """ "Only X may Y" is a restricted permission; it reads as a plain one.

    The restriction lives in the subject, and the subject is deliberately not
    interpreted.  A reviewer sees MAY where the source is closer to "MUST NOT,
    except for X".
    """
    assert polarities("Only accredited firms may disclose the data.", gb) == [("may", "")]


# ---------------------------------------------------------------------------
# False negatives
# ---------------------------------------------------------------------------


def test_known_false_negative_split_negation(gb):
    """ "is not only required to" defeats both the positive and negative cues."""
    assert polarities("The firm is not only required to file but also to publish.", gb) == []


def test_known_false_negative_elliptical_clause(gb):
    """ "...; the agent may not." has no predicate to carry, so it is dropped.

    Resolving the ellipsis means copying the predicate from the previous clause,
    which is a guess.  The site is claimed so the bare "may" underneath cannot
    surface a PERMISSION in its place — the inversion is the thing worth
    avoiding, not the miss.
    """
    assert polarities("The firm must file the report; the agent may not.", gb) == [("must", "")]


def test_known_false_negative_nominalised_duty(gb):
    """A duty expressed as a noun phrase carries no deontic operator."""
    assert polarities("Filing of the report is a requirement under the rules.", gb) == []


def test_known_false_negative_imperative(gb):
    """A bare imperative is an instruction with no modal to key on."""
    assert polarities("File the report before the deadline.", gb) == []


def test_known_false_negative_obligation_across_a_sentence_boundary(gb):
    """The clause never crosses a full stop, so a split duty loses its second half."""
    text = "The firm must act. It must do so promptly and in writing."
    found = polarities(text, gb)
    assert found == [("must", ""), ("must", "")]


def test_known_false_negative_third_language(gb):
    """Only English and Spanish are covered; a French duty is invisible."""
    assert polarities("L'entreprise doit conserver les registres.", gb) == []


# ---------------------------------------------------------------------------
# Things it does get right that are easy to break
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The firm must not disclose it.", "must_not"),
        ("The firm may not disclose it.", "must_not"),
        ("The firm is not required to disclose it.", "need_not"),
        ("The firm is required not to disclose it.", "must_not"),
        ("Neither the firm nor the agent may disclose it.", "must_not"),
        ("No employee may disclose it.", "must_not"),
        ("The firm must never disclose it.", "must_not"),
        ("The firm should not disclose it.", "should:negative"),
    ],
)
def test_negation_scope_never_inverts(gb, text, expected):
    assert polarities(text, gb)[0][0] == expected


@pytest.mark.parametrize(
    "text",
    [
        "Must the firm file the report?",
        "It is unclear whether the firm must file the report.",
        "Nothing in this Article shall prevent the firm from charging a fee.",
        "The firm shall not be prohibited from charging a fee.",
        "The firm may not be required to publish the notice.",
    ],
)
def test_scope_it_cannot_resolve_is_flagged_rather_than_asserted(gb, text):
    assert all(flag == "true" for _, flag in polarities(text, gb))
