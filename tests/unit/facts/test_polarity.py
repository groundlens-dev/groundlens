"""Obligation polarity: canonicalisation, the ordering, and the full table.

The obligation check is the reason this library exists, so its semantics are
written out here as data rather than derived.  A future reader should be able
to review what the product believes about deontic wording by reading two
tables, without running anything and without reconstructing an algorithm in
their head.

Two things are pinned:

* :data:`POLARITY_TABLE` — every ordered pair of the five polarities, with the
  :class:`~groundlens.types.MatchState` the matcher must return for it.
* :data:`OVERSTATEMENT_TABLE` — the same grid, saying which of those pairs the
  ``obligation_polarity_consistent`` assertion is entitled to fail on.

They are deliberately not computed from a rule.  If a change to the matcher
makes a cell move, the diff shows a reviewer exactly which sentence pair now
behaves differently.
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


# ---------------------------------------------------------------------------
# canonical_polarity — the named function every comparison goes through
# ---------------------------------------------------------------------------


def test_the_bare_enum_values_canonicalise() -> None:
    from groundlens.facts.polarity import canonical_polarity
    from groundlens.types import Polarity

    for member in Polarity:
        canonical = canonical_polarity(member.value)
        assert canonical is not None
        assert canonical.polarity is member
        assert canonical.negated is False
        assert canonical.value == member.value


def test_the_decorated_negative_recommendation_canonicalises() -> None:
    """``should:negative`` is a form the extractor really emits."""
    from groundlens.facts.polarity import canonical_polarity
    from groundlens.types import Polarity

    canonical = canonical_polarity("should:negative")
    assert canonical is not None
    assert canonical.polarity is Polarity.SHOULD
    assert canonical.negated is True
    assert canonical.value == "should:negative"


def test_the_extractor_really_emits_the_decorated_form(gb) -> None:
    """Pins the producer against the consumer, not just the consumer.

    If the extractor ever stops writing ``should:negative``, or starts
    writing something else, this fails here rather than silently degrading
    the check to UNCHECKABLE in production.
    """
    from groundlens.facts import extract_facts
    from groundlens.facts.polarity import canonical_polarity

    facts = extract_facts("The firm should not publish the note.", locale=gb, reference_date=REF)
    obligations = [fact for fact in facts if fact.kind.value == "obligation"]
    assert [fact.normalised for fact in obligations] == ["should:negative"]
    assert canonical_polarity(obligations[0].normalised) is not None


def test_canonicalisation_round_trips() -> None:
    from groundlens.facts.polarity import canonical_polarity

    for text in ("must", "must_not", "may", "need_not", "should", "should:negative"):
        canonical = canonical_polarity(text)
        assert canonical is not None
        assert canonical.value == text
        assert canonical_polarity(canonical.value) == canonical


def test_whitespace_and_case_carry_no_meaning() -> None:
    from groundlens.facts.polarity import canonical_polarity

    assert canonical_polarity("  MUST_NOT ") == canonical_polarity("must_not")


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "may (may)",  # the rendered form that used to reach the strength lookup
        "must_not (must not)",
        "should:positive",
        "should:negative:negative",
        "shall",
        "must not",  # a space, not the enum's underscore
        "P30D",
    ],
)
def test_a_value_this_library_did_not_write_is_refused(value) -> None:
    """``None`` out, never a guessed strength.

    Every caller turns ``None`` into UNCHECKABLE.  Guessing here would put a
    made-up strength into the one comparison the product is sold on.
    """
    from groundlens.facts.polarity import canonical_polarity, polarity_strength

    assert canonical_polarity(value) is None
    assert polarity_strength(value) is None


# ---------------------------------------------------------------------------
# the ordering — defined exactly once
# ---------------------------------------------------------------------------


def test_the_ordering_covers_every_polarity() -> None:
    from groundlens.facts.polarity import POLARITY_STRENGTH
    from groundlens.types import Polarity

    assert set(POLARITY_STRENGTH) == set(Polarity)


def test_the_ordering_is_what_the_product_claims() -> None:
    """Obligation and prohibition tie; recommendation, permission, exemption fall."""
    from groundlens.facts.polarity import polarity_strength

    must = polarity_strength("must")
    must_not = polarity_strength("must_not")
    should = polarity_strength("should")
    may = polarity_strength("may")
    need_not = polarity_strength("need_not")

    assert must == must_not
    assert must > should > may > need_not
    assert polarity_strength("should:negative") == should


def test_there_is_only_one_ordering_in_the_source() -> None:
    """No module may keep a private copy of the strength table.

    Two orderings is how the wedge check broke: the extractor emitted a value
    the assertion's own table could not read, and the mismatch degraded to
    UNCHECKABLE without anything failing.
    """
    import pathlib

    import groundlens

    root = pathlib.Path(groundlens.__file__).parent
    owner = root / "facts" / "polarity.py"
    offenders = [
        path
        for path in root.rglob("*.py")
        if path != owner
        and "POLARITY_STRENGTH" in path.read_text(encoding="utf-8")
        and "polarity.POLARITY_STRENGTH" not in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"a second strength ordering lives in {offenders}"


# ---------------------------------------------------------------------------
# the cross-product, written out
# ---------------------------------------------------------------------------

SENTENCE = {
    "MUST": "The firm must retain the records.",
    "MUST_NOT": "The firm must not retain the records.",
    "MAY": "The firm may retain the records.",
    "NEED_NOT": "The firm need not retain the records.",
    "SHOULD": "The firm should retain the records.",
}
"""One act, five operators.  The governed clause is identical in all five, so
the matcher's context gate is wide open and nothing but the polarity decides
the outcome."""

POLARITY_TABLE: dict[tuple[str, str], str] = {
    # (answer, evidence): expected MatchState
    #
    # The diagonal matches.  Everything off it is a contradiction, because the
    # evidence demonstrably says something other than what the answer says
    # about the same act.  Whether that difference is worth escalating on is
    # the rule pack's decision, not the matcher's — see OVERSTATEMENT_TABLE.
    ("MUST", "MUST"): "matched",
    ("MUST", "MUST_NOT"): "contradicted",  # inversion: required vs forbidden
    ("MUST", "MAY"): "contradicted",  # the wedge: duty asserted over discretion
    ("MUST", "NEED_NOT"): "contradicted",  # inversion: required vs exempt
    ("MUST", "SHOULD"): "contradicted",  # duty asserted over a recommendation
    ("MUST_NOT", "MUST"): "contradicted",  # inversion
    ("MUST_NOT", "MUST_NOT"): "matched",
    ("MUST_NOT", "MAY"): "contradicted",  # the wedge, reported in bug 1
    ("MUST_NOT", "NEED_NOT"): "contradicted",  # prohibition asserted over exemption
    ("MUST_NOT", "SHOULD"): "contradicted",
    ("MAY", "MUST"): "contradicted",  # answer understates a duty
    ("MAY", "MUST_NOT"): "contradicted",  # permission asserted over a prohibition
    ("MAY", "MAY"): "matched",
    ("MAY", "NEED_NOT"): "contradicted",  # permission asserted where only exemption is given
    ("MAY", "SHOULD"): "contradicted",  # answer understates a recommendation
    ("NEED_NOT", "MUST"): "contradicted",  # inversion, high value: exempts a duty
    ("NEED_NOT", "MUST_NOT"): "contradicted",
    ("NEED_NOT", "MAY"): "contradicted",
    ("NEED_NOT", "NEED_NOT"): "matched",
    ("NEED_NOT", "SHOULD"): "contradicted",
    ("SHOULD", "MUST"): "contradicted",  # answer understates a duty
    ("SHOULD", "MUST_NOT"): "contradicted",
    ("SHOULD", "MAY"): "contradicted",  # recommendation asserted over permission
    ("SHOULD", "NEED_NOT"): "contradicted",
    ("SHOULD", "SHOULD"): "matched",
}

OVERSTATEMENT_TABLE: dict[tuple[str, str], bool] = {
    # (answer, evidence): does obligation_polarity_consistent fail on it?
    #
    # True where the answer removes discretion the evidence leaves, or points
    # the opposite way at the same strength.  False where the answer is merely
    # weaker than the evidence: understating is a different defect and this
    # rule is not the one that catches it.
    ("MUST", "MUST"): False,
    ("MUST", "MUST_NOT"): True,
    ("MUST", "MAY"): True,
    ("MUST", "NEED_NOT"): True,
    ("MUST", "SHOULD"): True,
    ("MUST_NOT", "MUST"): True,
    ("MUST_NOT", "MUST_NOT"): False,
    ("MUST_NOT", "MAY"): True,
    ("MUST_NOT", "NEED_NOT"): True,
    ("MUST_NOT", "SHOULD"): True,
    ("MAY", "MUST"): False,
    ("MAY", "MUST_NOT"): False,
    ("MAY", "MAY"): False,
    ("MAY", "NEED_NOT"): True,
    ("MAY", "SHOULD"): False,
    ("NEED_NOT", "MUST"): False,
    ("NEED_NOT", "MUST_NOT"): False,
    ("NEED_NOT", "MAY"): False,
    ("NEED_NOT", "NEED_NOT"): False,
    ("NEED_NOT", "SHOULD"): False,
    ("SHOULD", "MUST"): False,
    ("SHOULD", "MUST_NOT"): False,
    ("SHOULD", "MAY"): True,
    ("SHOULD", "NEED_NOT"): True,
    ("SHOULD", "SHOULD"): False,
}

CANONICAL = {
    "MUST": "must",
    "MUST_NOT": "must_not",
    "MAY": "may",
    "NEED_NOT": "need_not",
    "SHOULD": "should",
}


def match_polarity(answer_key: str, evidence_key: str, profile):
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    facts = extract_facts(SENTENCE[answer_key], locale=profile, reference_date=REF)
    obligations = [fact for fact in facts if fact.kind.value == "obligation"]
    assert len(obligations) == 1, f"{answer_key}: expected one obligation, got {obligations}"
    matches = match_facts(
        obligations,
        [Evidence(id="doc-1#p0", text=SENTENCE[evidence_key])],
        locale=profile,
        config=MatchConfig(reference_date=REF),
    )
    assert len(matches) == 1
    return matches[0]


def test_the_table_is_the_whole_cross_product() -> None:
    assert len(POLARITY_TABLE) == 25
    assert set(POLARITY_TABLE) == {(a, b) for a in SENTENCE for b in SENTENCE}
    assert set(OVERSTATEMENT_TABLE) == set(POLARITY_TABLE)


@pytest.mark.parametrize(("answer_key", "evidence_key"), sorted(POLARITY_TABLE))
def test_the_polarity_cross_product(answer_key, evidence_key, gb) -> None:
    expected = POLARITY_TABLE[(answer_key, evidence_key)]
    match = match_polarity(answer_key, evidence_key, gb)
    assert match.state.value == expected, (
        f"{SENTENCE[answer_key]!r} against {SENTENCE[evidence_key]!r}"
    )


@pytest.mark.parametrize(("answer_key", "evidence_key"), sorted(POLARITY_TABLE))
def test_a_contradiction_carries_the_clean_canonical_evidence_value(
    answer_key, evidence_key, gb
) -> None:
    """The regression that broke the wedge check: ``"may (may)"``.

    ``evidence_value`` is read by the assertion, not only by a human, so it
    holds the canonical polarity and nothing else.
    """
    from groundlens.facts.polarity import canonical_polarity

    match = match_polarity(answer_key, evidence_key, gb)
    if match.state.value != "contradicted":
        return
    assert match.evidence_value == CANONICAL[evidence_key]
    assert canonical_polarity(match.evidence_value) is not None
    assert match.evidence_id == "doc-1#p0"
    assert match.evidence_span is not None


@pytest.mark.parametrize(("answer_key", "evidence_key"), sorted(OVERSTATEMENT_TABLE))
def test_the_overstatement_cross_product(answer_key, evidence_key) -> None:
    from groundlens.facts.polarity import canonical_polarity, exceeds_or_inverts

    answer = canonical_polarity(CANONICAL[answer_key])
    evidence = canonical_polarity(CANONICAL[evidence_key])
    assert answer is not None
    assert evidence is not None
    assert exceeds_or_inverts(answer, evidence) is OVERSTATEMENT_TABLE[(answer_key, evidence_key)]


def test_a_negative_recommendation_inverts_a_positive_one() -> None:
    """Not in the grid: the enum has no SHOULD_NOT, so it is checked here.

    Equal strength, opposite direction.  A strength comparison alone reports
    no problem, which is why :func:`exceeds_or_inverts` also compares the
    canonical values.
    """
    from groundlens.facts.polarity import canonical_polarity, exceeds_or_inverts

    positive = canonical_polarity("should")
    negative = canonical_polarity("should:negative")
    assert positive is not None
    assert negative is not None
    assert positive.strength == negative.strength
    assert exceeds_or_inverts(positive, negative) is True
    assert exceeds_or_inverts(negative, positive) is True
    assert exceeds_or_inverts(positive, positive) is False


# ---------------------------------------------------------------------------
# uncertainty stays uncertainty
# ---------------------------------------------------------------------------


def test_evidence_silent_on_the_act_is_not_a_contradiction(gb) -> None:
    """The evidence has obligations, just none about this act."""
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    facts = extract_facts(SENTENCE["MUST"], locale=gb, reference_date=REF)
    matches = match_facts(
        [fact for fact in facts if fact.kind.value == "obligation"],
        [Evidence(id="d", text="The customer may cancel the direct debit at any time.")],
        locale=gb,
        config=MatchConfig(reference_date=REF),
    )
    assert matches[0].state.value == "unmatched"
    assert matches[0].evidence_value is None


def test_an_unresolvable_negation_scope_is_uncheckable(gb) -> None:
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    # "must not prevent" — a prohibition on a prohibition. Which way round the
    # duty points depends on how the second negation scopes, and the extractor
    # does not try to resolve that.
    answer = "The firm must not prevent the customer from retaining the records."
    facts = [
        fact
        for fact in extract_facts(answer, locale=gb, reference_date=REF)
        if fact.kind.value == "obligation"
    ]
    assert facts, "expected the double negation to still produce an obligation"
    assert dict(facts[0].attrs).get("scope_uncertain") == "true"
    matches = match_facts(
        facts,
        [Evidence(id="d", text="The firm may prevent the customer from retaining the records.")],
        locale=gb,
        config=MatchConfig(reference_date=REF),
    )
    assert matches[0].state.value == "uncheckable"


def test_a_condition_in_the_evidence_only_is_uncheckable(gb) -> None:
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    facts = [
        fact
        for fact in extract_facts(
            "The firm must notify the customer.", locale=gb, reference_date=REF
        )
        if fact.kind.value == "obligation"
    ]
    matches = match_facts(
        facts,
        [Evidence(id="d", text="If the account is closed, the firm must notify the customer.")],
        locale=gb,
        config=MatchConfig(reference_date=REF),
    )
    assert matches[0].state.value == "uncheckable"


def test_an_unreadable_polarity_in_the_answer_is_uncheckable(gb) -> None:
    """The fail-safe, exercised by hand-building the Fact the extractor cannot.

    If some future cue writes a polarity this library cannot canonicalise, the
    answer is "we cannot tell", not "no contradiction" and not "contradicted".
    """
    from groundlens.facts import MatchConfig, match_facts
    from groundlens.types import Evidence, Fact, FactKind

    fact = Fact(
        kind=FactKind.OBLIGATION,
        raw="The firm shall-ish retain the records",
        span=(0, 37),
        normalised="shall_ish",
        attrs=(("polarity", "shall_ish"), ("predicate_key", "records retain")),
    )
    matches = match_facts(
        [fact],
        [Evidence(id="d", text=SENTENCE["MAY"])],
        locale=gb,
        config=MatchConfig(reference_date=REF),
    )
    assert matches[0].state.value == "uncheckable"
    assert matches[0].evidence_value is None
