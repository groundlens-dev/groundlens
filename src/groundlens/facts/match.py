"""Match extracted facts against evidence.

``match_facts`` takes the facts pulled out of an answer and decides, for each
one, whether the evidence supports it, contradicts it, is silent about it, or
leaves it undecidable.

Two rules shape everything here.

**A match is a span, not a document.**  Every ``MATCHED`` and ``CONTRADICTED``
result names an evidence id *and* a character span inside that item.  A
"match" against a four-thousand-token chunk tells a reviewer nothing and cannot
be audited, so it is never emitted.  Evidence is re-extracted with the same
extractor as the answer, and the span reported is the evidence fact's own span.

**CONTRADICTED is the product.**  A wrong number inside an otherwise correct
sentence is the defect class this library exists to catch, and it is far more
useful to a reviewer than "not found".  So the matcher does not stop at
value equality: when a same-kind fact sits in evidence whose surrounding words
line up with the answer's, but whose value differs, that is reported as a
contradiction with the evidence's value attached.  The context gate is what
keeps that from firing on every unrelated number in the corpus; without it the
false-positive rate is not shippable, and it can only be disabled explicitly.

Obligation polarity is compared the same way: an answer that says MUST where
the evidence says MAY is ``CONTRADICTED``, not ``UNMATCHED``.  That is the
highest-value check in the library and the reason the extractor keeps polarity
as a first-class typed value instead of a lexical flag.

No floats.  Tolerances arrive as decimal strings and are compared with
``decimal.Decimal`` inside a fixed context.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext
from typing import TYPE_CHECKING, Final

from groundlens.facts.config import MatchConfig, as_decimal
from groundlens.facts.extract import extract_facts
from groundlens.facts.polarity import canonical_polarity
from groundlens.types import Fact, FactKind, Match, MatchState

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping, Sequence
    from datetime import date

    from groundlens.determinism import LocaleProfile
    from groundlens.types import Evidence

__all__ = ["match_facts"]

_CTX: Final[Context] = Context(prec=34)

_NUMERIC_KINDS: Final[frozenset[FactKind]] = frozenset(
    {FactKind.NUMBER, FactKind.PERCENT, FactKind.CURRENCY}
)

BLOCKING_AMBIGUITIES: Final[frozenset[str]] = frozenset(
    {
        "currency_symbol_ambiguous",
        "currency_word_ambiguous",
        "multiplier_ambiguous",
        "unparsable",
        "invalid_date",
    }
)
"""Readings the profile could not settle at all.  Never contradicted on these."""

SOFT_AMBIGUITIES: Final[frozenset[str]] = frozenset(
    {
        "date_order_ambiguous",
        "grouping_malformed",
        "grouping_vs_decimal",
        "separator_repeated",
        "two_digit_year",
        "year_inferred",
    }
)
"""Readings resolved by a documented rule.

Good enough to confirm a match, not good enough to accuse the answer of
contradicting the evidence: the apparent difference may be our reading, not the
author's error.  A candidate contradiction carrying one of these is downgraded
to ``UNCHECKABLE`` so a human looks rather than the pipeline escalating on a
separator convention.
"""


@dataclass(frozen=True, slots=True)
class _Candidate:
    evidence_id: str
    fact: Fact
    score: Decimal
    equal: bool
    crossed: bool = False

    @property
    def sort_key(self) -> tuple[int, int, str, str, int, int]:
        # Higher score first (negated via the sign of the scaled integer), then
        # a same-kind witness ahead of a crossed-kind one, then a stable lexical
        # tie-break.  No float, no set ordering.
        #
        # The crossing exists so a deadline can be decided at all; it is not a
        # better witness than the evidence's own deadline.  A source that says
        # "the period ends on 2026-08-22" and also mentions the agreement date
        # must be quoted on the end date, not on the agreement date.
        scaled = int((self.score * 1_000_000).to_integral_value())
        return (
            -scaled,
            int(self.crossed),
            self.evidence_id,
            self.fact.normalised,
            *self.fact.span,
        )


def match_facts(
    facts: Sequence[Fact],
    evidence: Sequence[Evidence],
    *,
    locale: LocaleProfile,
    config: MatchConfig | Mapping[str, object] | None = None,
) -> tuple[Match, ...]:
    """Decide the state of every fact against the evidence.

    Args:
        facts: Facts extracted from the answer, as returned by
            :func:`groundlens.facts.extract.extract_facts`.
        evidence: Evidence items.  Their ``text`` must already be
            NFKC-normalised, exactly as for the answer.
        locale: Locale profile.  Must be the one used to extract ``facts``;
            using a different profile would compare two different readings.
        config: A :class:`~groundlens.facts.config.MatchConfig` or the mapping a
            rule pack carries under ``facts:``.  Tolerances are decimal strings.

    Returns:
        One :class:`~groundlens.types.Match` per input fact, in the input order.

    Raises:
        ValueError: If relative deadlines are present and no reference date is
            available from the config or from the facts.  The clock is never
            read to fill that gap.
    """
    cfg = MatchConfig.coerce(config)
    matches: list[Match] = []
    if not facts:
        return ()

    reference_date = cfg.reference_date or _reference_date_from(facts)
    index = _index_evidence(evidence, locale, cfg, reference_date)

    for fact in facts:
        matches.append(_match_one(fact, index, cfg))
    return tuple(matches)


# ---------------------------------------------------------------------------
# Evidence indexing
# ---------------------------------------------------------------------------


def _reference_date_from(facts: Sequence[Fact]) -> date:
    from datetime import date as _date

    for fact in facts:
        attrs = dict(fact.attrs)
        stamp = attrs.get("reference_date")
        if stamp:
            try:
                return _date.fromisoformat(stamp)
            except ValueError:  # pragma: no cover - extractor writes ISO
                continue
    needs_anchor = any(fact.kind is FactKind.DEADLINE for fact in facts)
    if needs_anchor:
        raise ValueError(
            "match_facts needs a reference_date to resolve relative deadlines in the "
            "evidence; pass MatchConfig(reference_date=...). The system clock is never "
            "used as a fallback."
        )
    return _date(1970, 1, 1)


def _index_evidence(
    evidence: Sequence[Evidence],
    locale: LocaleProfile,
    cfg: MatchConfig,
    reference_date: date,
) -> tuple[tuple[str, tuple[Fact, ...]], ...]:
    ordered = sorted(
        ((item.id, item.text) for item in evidence), key=lambda pair: (pair[0], pair[1])
    )
    out: list[tuple[str, tuple[Fact, ...]]] = []
    for evidence_id, text in ordered:
        if not text:
            out.append((evidence_id, ()))
            continue
        out.append(
            (
                evidence_id,
                extract_facts(
                    text[: cfg.max_evidence_chars],
                    locale=locale,
                    reference_date=reference_date,
                ),
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# Per-fact decision
# ---------------------------------------------------------------------------


def _match_one(
    fact: Fact,
    index: tuple[tuple[str, tuple[Fact, ...]], ...],
    cfg: MatchConfig,
) -> Match:
    attrs = dict(fact.attrs)
    ambiguities = frozenset(a for a in attrs.get("ambiguity", "").split(",") if a)

    equal: list[_Candidate] = []
    differing: list[_Candidate] = []
    for evidence_id, evidence_facts in index:
        for candidate in evidence_facts:
            if not _comparable_kinds(fact.kind, candidate.kind):
                continue
            verdict = _compare(fact, candidate, cfg)
            if verdict is None:
                continue
            is_equal, score = verdict
            entry = _Candidate(
                evidence_id, candidate, score, is_equal, candidate.kind is not fact.kind
            )
            (equal if is_equal else differing).append(entry)

    if equal:
        best = min(equal, key=lambda c: c.sort_key)
        state = _conditionality_check(fact, best.fact, cfg)
        return Match(
            fact=fact,
            state=state,
            evidence_id=best.evidence_id,
            evidence_span=best.fact.span,
            evidence_value=(
                _evidence_value(best.fact) if state is MatchState.UNCHECKABLE else None
            ),
        )

    if fact.normalised == "" or ambiguities & BLOCKING_AMBIGUITIES:
        return Match(fact=fact, state=MatchState.UNCHECKABLE)
    if attrs.get("scope_uncertain") == "true":
        return Match(fact=fact, state=MatchState.UNCHECKABLE)
    if fact.kind is FactKind.OBLIGATION and canonical_polarity(fact.normalised) is None:
        # The answer's own operator is not one this library can read.  Saying
        # nothing about its strength is the only defensible answer.
        return Match(fact=fact, state=MatchState.UNCHECKABLE)

    if differing:
        viable = [c for c in differing if c.score >= _threshold(fact, c.fact, cfg)]
        if viable:
            best = min(viable, key=lambda c: c.sort_key)
            candidate_ambiguities = frozenset(
                a for a in dict(best.fact.attrs).get("ambiguity", "").split(",") if a
            )
            soft = (ambiguities | candidate_ambiguities) & SOFT_AMBIGUITIES
            if soft or dict(best.fact.attrs).get("scope_uncertain") == "true":
                return Match(
                    fact=fact,
                    state=MatchState.UNCHECKABLE,
                    evidence_id=best.evidence_id,
                    evidence_span=best.fact.span,
                    evidence_value=_evidence_value(best.fact),
                )
            return Match(
                fact=fact,
                state=MatchState.CONTRADICTED,
                evidence_id=best.evidence_id,
                evidence_span=best.fact.span,
                evidence_value=_evidence_value(best.fact),
            )

    if fact.kind is FactKind.DEADLINE and _unresolved_deadline(fact):
        # The answer states a relative deadline that never resolved to a day —
        # no reference date was supplied, or the count is in business days and
        # this library has no holiday calendar.  "No source says this" would be
        # a claim about the evidence; the truth is that we could not check.
        return Match(fact=fact, state=MatchState.UNCHECKABLE)
    return Match(fact=fact, state=MatchState.UNMATCHED)


def _comparable_kinds(fact_kind: FactKind, candidate_kind: FactKind) -> bool:
    """Whether a fact of one kind may be decided against a candidate of another.

    Same kind against same kind, plus one deliberate crossing: a DEADLINE may
    be decided against a DATE.  A source almost never repeats the answer's
    deadline wording — it writes "the period ends on 2026-08-22" where the
    answer writes "by 2026-08-31" — so a same-kind-only matcher leaves every
    such deadline UNMATCHED and ``fact.contradicted.deadline`` unreachable.
    What the two share is a resolved due date, and that is what is compared.
    """
    if fact_kind is candidate_kind:
        return True
    return fact_kind is FactKind.DEADLINE and candidate_kind is FactKind.DATE


def _resolved_due_date(fact: Fact) -> str:
    """The full ISO day this fact resolves to, or ``""`` when it does not.

    A DEADLINE carries it in ``attrs["due_date"]``, written by the extractor
    when it resolved the expression against the reference date or read an
    explicit date.  A DATE *is* one.  Partial values ("--08-31", "2026-08")
    return ``""``: a day that is only partly known cannot contradict a day that
    is fully known, and comparing the two as strings would say it could.
    """
    value = fact.normalised if fact.kind is FactKind.DATE else dict(fact.attrs).get("due_date", "")
    return value if len(value) == 10 and value[4] == "-" and value[7] == "-" else ""


def _unresolved_deadline(fact: Fact) -> bool:
    """A relative deadline the extractor could not turn into a day.

    An event-anchored deadline ("within 30 days of receipt") is excluded: it is
    unresolved as a date but perfectly comparable as a duration, and that
    comparison is the one the matcher makes for it.
    """
    attrs = dict(fact.attrs)
    if attrs.get("anchor") == "event":
        return False
    return bool(attrs.get("duration")) and not _resolved_due_date(fact)


def _threshold(fact: Fact, candidate: Fact, cfg: MatchConfig) -> Decimal:
    """Context score a differing candidate must reach to count as a contradiction.

    The gate exists because documents are full of same-kind values and a bare
    clash between two of them says nothing.  Two resolved due dates are the one
    case where that is not true: a due date is only produced from an explicit
    deadline frame ("by X", "no later than X", "within N days of Y"), and that
    frame is itself the context.  Requiring the surrounding words to overlap as
    well would gate out precisely the paraphrase this crossing exists for —
    "tell us by 2026-08-31" against "the period ends on 2026-08-22" share a
    claim and not one content word.
    """
    if fact.kind is FactKind.OBLIGATION:
        return as_decimal(cfg.obligation_similarity_min, default="0.5")
    if not cfg.contradiction_requires_context:
        return Decimal(0)
    if (
        fact.kind is FactKind.DEADLINE
        and _resolved_due_date(fact)
        and _resolved_due_date(candidate)
    ):
        return Decimal(0)
    return as_decimal(cfg.context_similarity_min, default="0.34")


def _conditionality_check(fact: Fact, candidate: Fact, cfg: MatchConfig) -> MatchState:
    """Same polarity, different applicability, is not the same obligation.

    "You must notify us" and "if you close the account, you must notify us" say
    different things.  Reported as ``UNCHECKABLE`` rather than ``MATCHED``: the
    condition may well be implied elsewhere in the answer, so calling it a
    contradiction would over-escalate.
    """
    if fact.kind is not FactKind.OBLIGATION or not cfg.conditional_mismatch_uncheckable:
        return MatchState.MATCHED
    answer_conditional = dict(fact.attrs).get("conditional") == "true"
    evidence_conditional = dict(candidate.attrs).get("conditional") == "true"
    if evidence_conditional and not answer_conditional:
        return MatchState.UNCHECKABLE
    return MatchState.MATCHED


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _compare(fact: Fact, candidate: Fact, cfg: MatchConfig) -> tuple[bool, Decimal] | None:
    """Compare two same-kind facts.

    Returns:
        ``(equal, context_score)``, or ``None`` when the two are not comparable
        at all (different currency, different day basis, different instrument)
        and so neither support nor contradict each other.
    """
    if fact.kind is FactKind.OBLIGATION:
        return _compare_obligation(fact, candidate)

    score = _context_score(fact, candidate)
    if fact.kind in _NUMERIC_KINDS:
        return _compare_numeric(fact, candidate, cfg, score)
    if fact.kind is FactKind.DATE:
        return _compare_date(fact, candidate, score)
    if fact.kind is FactKind.DURATION:
        return _compare_duration(fact, candidate, score)
    if fact.kind is FactKind.DEADLINE:
        return _compare_deadline(fact, candidate, score)
    if fact.kind is FactKind.CITATION:
        return _compare_citation(fact, candidate, score)
    return (fact.normalised == candidate.normalised, score)


def _compare_numeric(
    fact: Fact, candidate: Fact, cfg: MatchConfig, score: Decimal
) -> tuple[bool, Decimal] | None:
    left = _numeric_parts(fact)
    right = _numeric_parts(candidate)
    if left is None or right is None:
        return (fact.normalised == candidate.normalised, score)
    left_unit, left_value = left
    right_unit, right_value = right
    if left_unit != right_unit:
        # EUR versus USD, or percent versus percentage points: a different
        # quantity, not a wrong one.  Saying nothing beats saying the wrong
        # thing, but a same-unit-free amount clash is still worth surfacing.
        if fact.kind is FactKind.CURRENCY and left_value == right_value:
            return (False, score)
        return None
    with localcontext(_CTX):
        delta = abs(left_value - right_value)
        absolute = cfg.tolerance_for(fact.kind.value)
        relative = cfg.relative_tolerance_for(fact.kind.value)
        allowed = absolute
        if relative > 0:
            allowed = max(allowed, abs(right_value) * relative)
        return (delta <= allowed, score)


def _numeric_parts(fact: Fact) -> tuple[str, Decimal] | None:
    text = fact.normalised
    if not text:
        return None
    unit = ""
    if fact.kind is FactKind.CURRENCY:
        head, _, tail = text.partition(" ")
        unit, text = head, tail
    elif fact.kind is FactKind.PERCENT:
        if text.endswith("pp"):
            unit, text = "pp", text[:-2]
        elif text.endswith("%"):
            unit, text = "%", text[:-1]
    try:
        with localcontext(_CTX):
            return unit, Decimal(text)
    except InvalidOperation:
        return None


def _compare_date(fact: Fact, candidate: Fact, score: Decimal) -> tuple[bool, Decimal] | None:
    left, right = fact.normalised, candidate.normalised
    if not left or not right:
        return None
    if left == right:
        return (True, score)
    left_md, right_md = _month_day(left), _month_day(right)
    if left.startswith("--") or right.startswith("--"):
        # One side has no year.  Equal month/day supports; different month/day
        # contradicts; nothing else can be said.
        return (left_md == right_md, score)
    if len(left) == 7 or len(right) == 7:  # YYYY-MM precision
        return (left[:7] == right[:7], score)
    return (False, score)


def _month_day(value: str) -> str:
    return value[-5:]


def _basis_conflict(fact: Fact, candidate: Fact) -> bool:
    """Whether the two sides disagree about business versus calendar days.

    Thirty business days is not thirty days.  One side saying "business" while
    the other says nothing is treated as a disagreement, not as agreement.
    """
    left = dict(fact.attrs).get("day_basis", "")
    right = dict(candidate.attrs).get("day_basis", "")
    return "business" in {left, right} and left != right


def _compare_duration(fact: Fact, candidate: Fact, score: Decimal) -> tuple[bool, Decimal] | None:
    if _basis_conflict(fact, candidate):
        return (False, score)
    return (fact.normalised == candidate.normalised, score)


def _compare_deadline(fact: Fact, candidate: Fact, score: Decimal) -> tuple[bool, Decimal] | None:
    if candidate.kind is FactKind.DATE:
        # Cross-kind: only the resolved day is comparable, never the surface
        # text.  When the answer's deadline did not resolve there is nothing to
        # compare and the pair is refused rather than guessed at — an
        # unresolved deadline is never reported as contradicting a date.
        left_due, right_due = _resolved_due_date(fact), _resolved_due_date(candidate)
        if not left_due or not right_due:
            return None
        return (left_due == right_due, score)

    left = dict(fact.attrs)
    right = dict(candidate.attrs)
    left_duration, right_duration = left.get("duration", ""), right.get("duration", "")
    if left_duration and right_duration:
        # Compare the durations, not the resolved dates: one side may be
        # anchored to the reference date and the other to an event, and
        # "within 30 days" is still "within 30 days" either way.
        if _basis_conflict(fact, candidate):
            return (False, score)
        return (left_duration == right_duration, score)
    left_due, right_due = _resolved_due_date(fact), _resolved_due_date(candidate)
    if left_due and right_due:
        return (left_due == right_due, score)
    if fact.normalised == candidate.normalised:
        return (True, score)
    if left.get("anchor") != right.get("anchor"):
        # A deadline hanging off an event and one hanging off the reference
        # date are not the same measurement; refuse rather than guess.
        return None
    return (False, score)


def _compare_citation(fact: Fact, candidate: Fact, score: Decimal) -> tuple[bool, Decimal] | None:
    if fact.normalised == candidate.normalised:
        return (True, score)
    left_head, left_tail = _citation_parts(fact.normalised)
    right_head, right_tail = _citation_parts(candidate.normalised)
    if left_head and left_head == right_head and left_tail != right_tail:
        # Same instrument, different article: the highest-value citation defect.
        return (False, score)
    return None


def _citation_parts(value: str) -> tuple[str, str]:
    tokens = value.split()
    if len(tokens) < 2:
        return ("", value)
    return (" ".join(tokens[:-1]), tokens[-1])


def _compare_obligation(fact: Fact, candidate: Fact) -> tuple[bool, Decimal] | None:
    """Compare two obligations on their canonical polarity.

    Both sides are canonicalised first, so the decorated form the extractor
    writes for negative recommendations (``should:negative``) is understood
    here rather than being parsed at the comparison site.  A polarity neither
    side can canonicalise makes the pair incomparable, which surfaces as
    UNCHECKABLE — never as agreement and never as a contradiction.
    """
    left_polarity = canonical_polarity(fact.normalised)
    right_polarity = canonical_polarity(candidate.normalised)
    if left_polarity is None or right_polarity is None:
        return None
    left = dict(fact.attrs)
    right = dict(candidate.attrs)
    score = _containment(
        _token_set(left.get("predicate_key", "")),
        _token_set(right.get("predicate_key", "")),
    )
    if score == 0:
        # The evidence has obligations, but none of them is about this act.
        # Silence, not disagreement.
        return None
    return (left_polarity == right_polarity, score)


# ---------------------------------------------------------------------------
# Context scoring
# ---------------------------------------------------------------------------


def _context_score(fact: Fact, candidate: Fact) -> Decimal:
    return _containment(
        _token_set(dict(fact.attrs).get("context_key", "")),
        _token_set(dict(candidate.attrs).get("context_key", "")),
    )


def _token_set(key: str) -> frozenset[str]:
    return frozenset(token for token in key.split(" ") if token)


def _containment(left: frozenset[str], right: frozenset[str]) -> Decimal:
    """Overlap as a fraction of the smaller set.

    Containment rather than Jaccard: an evidence sentence is often much longer
    than the answer's, and Jaccard would penalise that length difference as if
    it were disagreement.
    """
    if not left or not right:
        return Decimal(0)
    overlap = len(left & right)
    if overlap == 0:
        return Decimal(0)
    with localcontext(_CTX):
        return Decimal(overlap) / Decimal(min(len(left), len(right)))


def _evidence_value(fact: Fact) -> str:
    """The evidence fact's value, as ``Match.evidence_value`` carries it.

    This slot is read by machines as well as by people: the
    ``obligation_polarity_consistent`` assertion looks the polarity up in
    :data:`~groundlens.facts.polarity.POLARITY_STRENGTH`.  So it holds the
    canonical value and never a rendering of it.  An obligation reports
    ``"may"``, not ``"may (may)"``: the parenthesis said nothing the canonical
    string did not already say, and it made the value unreadable to the one
    consumer that had to read it.

    The day-basis suffix stays, because it is not a rendering.  ``P30D`` cannot
    express "business days", so dropping it would lose the very distinction
    that made the two sides differ.
    """
    attrs = dict(fact.attrs)
    basis = attrs.get("day_basis")
    if fact.kind in {FactKind.DURATION, FactKind.DEADLINE} and basis == "business":
        return f"{fact.normalised} (business days)"
    if fact.kind is FactKind.OBLIGATION:
        canonical = canonical_polarity(fact.normalised)
        return fact.normalised if canonical is None else canonical.value
    return fact.normalised
