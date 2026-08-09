"""Deterministic fact extraction.

``extract_facts`` reads a piece of text and returns the checkable claims in it
as :class:`~groundlens.types.Fact` values.  Eight kinds are extracted and no
others: NUMBER, CURRENCY, PERCENT, DATE, DURATION, DEADLINE, CITATION and
OBLIGATION.

**The input must already be NFKC-normalised.**  Every ``span`` is a pair of
character offsets into the text exactly as passed in.  The caller is
responsible for running ``groundlens.determinism.normalise_text`` once, before
extraction, on both the answer and every evidence item; normalising twice here
would move offsets relative to the caller's copy and silently corrupt every
span in the audit record.  ``Fact.raw == text[span[0]:span[1]]`` always holds.

**No wall clock.**  Relative deadlines resolve against the ``reference_date``
argument.  ``date.today()`` is never called.

What is deliberately absent
---------------------------
There is no actor or named-entity extraction.  Deciding that "the firm" in an
answer is or is not "Acme Financial Services Ltd" in the evidence requires
coreference, alias tables, legal-entity suffix handling and transliteration.
Each of those manufactures false "unmatched actor" findings, and false
escalations are what get a checker switched off.  Subject text is carried
verbatim in ``attrs["subject_text"]`` for display only and is never matched on.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from groundlens.facts.config import ExtractConfig
from groundlens.facts.lexicon import (
    AMBIGUOUS_MARKERS,
    CARDINAL_BLOCKING_NEIGHBOURS,
    CARDINAL_WORDS,
    CONDITIONAL_MARKERS,
    CURRENCY_CODES,
    CURRENCY_SYMBOLS,
    CURRENCY_WORDS,
    DEONTIC_CUES,
    DOUBLE_NEGATION_HEADS,
    MONTHS,
    MULTIPLIERS,
    NEGATIVE_FORMS,
    SCOPE_HEDGES,
    STOPWORDS,
)
from groundlens.facts.normalise import (
    DATE_PATTERN,
    DURATION_PATTERN,
    NUMBER_PATTERN,
    Normalisation,
    add_duration,
    normalise_citation,
    normalise_currency,
    normalise_date,
    normalise_duration,
    normalise_number,
    normalise_percent,
)
from groundlens.types import Fact, FactKind, Polarity

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping
    from datetime import date

    from groundlens.determinism import LocaleProfile

__all__ = ["EXTRACTOR_VERSION", "extract_facts"]

EXTRACTOR_VERSION: Final[str] = "2"
"""Recorded in the audit record.  Bump on any change that moves a span."""

_MAX_CLAUSE_CHARS: Final[int] = 400
_MAX_CONDITION_CHARS: Final[int] = 240
_MAX_KEY_TOKENS: Final[int] = 32

# Priority decides which kind wins when two candidates cover the same
# characters and have the same length.  Lower is stronger.
_PRIORITY: Final[dict[FactKind, int]] = {
    FactKind.CITATION: 10,
    FactKind.CURRENCY: 20,
    FactKind.PERCENT: 30,
    FactKind.DEADLINE: 40,
    FactKind.DATE: 50,
    FactKind.DURATION: 60,
    FactKind.NUMBER: 90,
}


@dataclass(frozen=True, slots=True)
class _Candidate:
    start: int
    end: int
    kind: FactKind
    normalisation: Normalisation

    @property
    def length(self) -> int:
        return self.end - self.start


def extract_facts(
    text: str,
    *,
    locale: LocaleProfile,
    reference_date: date | None,
    config: ExtractConfig | Mapping[str, object] | None = None,
) -> tuple[Fact, ...]:
    """Extract checkable facts from already NFKC-normalised text.

    Args:
        text: The answer or evidence text.  Must already be NFKC-normalised by
            the caller; this function does not normalise it again.
        locale: Locale profile deciding decimal separator, group separator and
            date order.  The process environment is never consulted.
        reference_date: Anchor for relative deadlines ("within 30 days").
            Never defaulted from the system clock.  Pass ``None`` when the
            caller has no anchor: relative deadlines are then reported as plain
            durations rather than resolved against a date nobody supplied.
        config: An :class:`~groundlens.facts.config.ExtractConfig` or the
            mapping a rule pack carries under ``facts:``.

    Returns:
        Facts in document order, then by end offset, then by kind.  The tuple is
        the same for the same inputs on every run and every machine.
    """
    cfg = ExtractConfig.coerce(config)
    if not text:
        return ()

    candidates: list[_Candidate] = []
    candidates.extend(_citations(text))
    candidates.extend(_currencies(text, locale))
    candidates.extend(_percents(text, locale))
    candidates.extend(_deadlines(text, locale, reference_date))
    candidates.extend(_dates(text, locale))
    candidates.extend(_durations(text, locale))
    candidates.extend(_numbers(text, locale))
    candidates.extend(_cardinal_words(text, locale))

    accepted = _resolve_overlaps(candidates)
    facts = [_to_fact(text, c) for c in accepted if cfg.wants(c.kind.value)]

    if cfg.wants(FactKind.OBLIGATION.value):
        blocked = tuple((c.start, c.end) for c in accepted)
        facts.extend(_obligations(text, blocked, cfg))

    facts.sort(key=lambda f: (f.span[0], f.span[1], f.kind.value, f.normalised))
    return tuple(facts[: cfg.max_facts])


# ---------------------------------------------------------------------------
# Overlap resolution
# ---------------------------------------------------------------------------


def _resolve_overlaps(candidates: list[_Candidate]) -> list[_Candidate]:
    """Keep the longest, then strongest, non-overlapping candidate at each site.

    A DEADLINE swallows the DATE or DURATION inside it, a CURRENCY swallows its
    NUMBER and a CITATION swallows its article number.  Emitting both would
    double-count the same claim and produce two findings for one defect.
    """
    ordered = sorted(
        candidates,
        key=lambda c: (c.start, -c.length, _PRIORITY[c.kind], c.kind.value),
    )
    accepted: list[_Candidate] = []
    # ``ordered`` is sorted by start, so every accepted candidate starts at or
    # before this one: overlap reduces to "does any accepted interval reach
    # past my start".  Tracking the furthest end keeps this linear.
    furthest_end = 0
    for candidate in ordered:
        if candidate.start < furthest_end:
            continue
        accepted.append(candidate)
        furthest_end = max(furthest_end, candidate.end)
    return accepted


def _to_fact(text: str, candidate: _Candidate) -> Fact:
    attrs = dict(candidate.normalisation.attrs)
    if candidate.normalisation.ambiguities:
        attrs["ambiguity"] = ",".join(candidate.normalisation.ambiguities)
    # The context key travels with the fact so the matcher can decide
    # "same claim, different value" without being handed the source text again.
    sentence_start, sentence_end = _sentence_bounds(text, candidate.start, candidate.end)
    attrs["sentence_span"] = f"{sentence_start}:{sentence_end}"
    attrs["context_key"] = _key_tokens(
        text[sentence_start : candidate.start] + " " + text[candidate.end : sentence_end]
    )
    return Fact(
        kind=candidate.kind,
        raw=text[candidate.start : candidate.end],
        span=(candidate.start, candidate.end),
        normalised=candidate.normalisation.value,
        attrs=tuple(sorted(attrs.items())),
    )


# ---------------------------------------------------------------------------
# NUMBER / CURRENCY / PERCENT
# ---------------------------------------------------------------------------

_MULTIPLIER_ALT: Final[str] = "|".join(sorted(MULTIPLIERS, key=len, reverse=True))
_SYMBOLS: Final[frozenset[str]] = frozenset(CURRENCY_SYMBOLS) | frozenset(
    marker for marker in AMBIGUOUS_MARKERS if not marker[0].isalpha()
)
_CURRENCY_TEXT_MARKERS: Final[frozenset[str]] = frozenset(CURRENCY_WORDS) | frozenset(
    marker for marker in AMBIGUOUS_MARKERS if marker[0].isalpha()
)
_SYMBOL_ALT: Final[str] = "|".join(re.escape(s) for s in sorted(_SYMBOLS, key=len, reverse=True))
_CODE_ALT: Final[str] = "|".join(sorted(CURRENCY_CODES))
_WORD_ALT: Final[str] = "|".join(
    re.escape(w) for w in sorted(_CURRENCY_TEXT_MARKERS, key=len, reverse=True)
)
_MULT_GROUP: Final[str] = rf"(?:\s*(?P<mult>{_MULTIPLIER_ALT})\b)?"

_CURRENCY_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?P<cur>{_SYMBOL_ALT}|\b(?:{_CODE_ALT})\b)\s*(?P<amt>{NUMBER_PATTERN}){_MULT_GROUP}"
)
_CURRENCY_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?P<amt>{NUMBER_PATTERN}){_MULT_GROUP}\s*"
    rf"(?P<cur>{_SYMBOL_ALT}|\b(?:{_CODE_ALT})\b|\b(?:{_WORD_ALT})\b)",
    re.IGNORECASE,
)
_PERCENT_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?P<amt>{NUMBER_PATTERN})\s*"
    r"(?P<unit>%|percentage\s+points?|puntos?\s+porcentuales?|per\s?cent(?:age)?|percent|"
    r"pct|por\s+ciento)",
    re.IGNORECASE,
)
_NUMBER_RE: Final[re.Pattern[str]] = re.compile(NUMBER_PATTERN)


def _currencies(text: str, locale: LocaleProfile) -> list[_Candidate]:
    out: list[_Candidate] = []
    for pattern in (_CURRENCY_PREFIX_RE, _CURRENCY_SUFFIX_RE):
        for match in pattern.finditer(text):
            token = match.group("cur")
            # "usd" lower-cased in prose is more often a typo than a code;
            # the suffix pattern is case-insensitive so guard it here.
            if (
                token.upper() in CURRENCY_CODES
                and token != token.upper()
                and token.lower() not in CURRENCY_WORDS
            ):
                continue
            normalisation = normalise_currency(
                match.group("amt"), token, locale, multiplier=match.groupdict().get("mult")
            )
            out.append(_Candidate(match.start(), match.end(), FactKind.CURRENCY, normalisation))
    return out


def _percents(text: str, locale: LocaleProfile) -> list[_Candidate]:
    out: list[_Candidate] = []
    for match in _PERCENT_RE.finditer(text):
        unit = " ".join(match.group("unit").lower().split())
        points = unit.startswith("percentage point") or unit.startswith("punto")
        normalisation = normalise_percent(match.group("amt"), locale, percentage_points=points)
        out.append(_Candidate(match.start(), match.end(), FactKind.PERCENT, normalisation))
    return out


def _numbers(text: str, locale: LocaleProfile) -> list[_Candidate]:
    out: list[_Candidate] = []
    for match in _NUMBER_RE.finditer(text):
        normalisation = normalise_number(match.group(0), locale)
        if not normalisation.ok:
            continue
        out.append(_Candidate(match.start(), match.end(), FactKind.NUMBER, normalisation))
    return out


# ---------------------------------------------------------------------------
# NUMBER written as a word
# ---------------------------------------------------------------------------
#
# "three" and "3" must land on the same canonical string or a wrong spelled-out
# count produces no fact and no rule can act on it.  The table is in
# lexicon.CARDINAL_WORDS and the note there records which constructions were
# left out.  Everything below is a *refusal*: each guard drops a match rather
# than reading it, because on this corpus a false NUMBER on clean traffic costs
# more than a missed one on a defect.
#
# A cardinal word is only ever a NUMBER, never a DURATION, CURRENCY or PERCENT.
# Those three kinds are built on the digit pattern, and reaching into them from
# here would change what "3 %" and "30 days" already extract as.  Where the
# word form would land in a different kind from the digit form the word form is
# dropped instead (see _CARDINAL_UNIT_TAIL_RE); the one exception is a duration
# unit, because "the first three years" is the count this library is asked to
# compare against "the first five years".

_CARDINAL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:" + "|".join(sorted(CARDINAL_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_ALPHA_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+", re.UNICODE)
_DASHES: Final[str] = "-\u2010\u2011\u2012\u2013\u2014"
"""Hyphen-minus plus the Unicode hyphens and dashes NFKC leaves alone."""
_CARDINAL_COORDINATORS: Final[frozenset[str]] = frozenset({"and", "y"})
_CARDINAL_NEIGHBOUR_CHARS: Final[int] = 24

_CARDINAL_UNIT_TAIL_RE: Final[re.Pattern[str]] = re.compile(
    r"\s{0,2}(?:%|percentage\s+points?|puntos?\s+porcentuales?|per\s?cent(?:age)?|"
    rf"percent|pct|por\s+ciento|{_SYMBOL_ALT}|(?:{_CODE_ALT})\b|(?:{_WORD_ALT})\b)",
    re.IGNORECASE,
)
"""A unit that would have made the digit form a PERCENT or a CURRENCY.

``3 %`` is a PERCENT and ``3 EUR`` is a CURRENCY, so emitting a bare NUMBER for
``three %`` would leave the two spellings of the same claim in different kinds
and unable to match.  The word form is dropped instead."""

_CARDINAL_HEAD_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?:{_SYMBOL_ALT}|\b(?:{_CODE_ALT}))\s{{0,2}}$"
)
"""Same, for a currency marker sitting in front of the word ("EUR three")."""


def _cardinal_words(text: str, locale: LocaleProfile) -> list[_Candidate]:
    out: list[_Candidate] = []
    for match in _CARDINAL_RE.finditer(text):
        raw = match.group(0)
        if len(raw) > 1 and raw.isupper():
            # "DOS" and "SEIS" in an upper-cased identifier are not counts.
            continue
        start, end = match.start(), match.end()
        # A hyphen either side means a compound, not this word:
        # "twenty-three", "two-thirds".  Written out rather than as a slice
        # test because an empty slice is a substring of every string.
        if start > 0 and text[start - 1] in _DASHES:
            continue
        if end < len(text) and text[end] in _DASHES:
            continue
        if _cardinal_neighbour_blocks(text, start, end):
            continue
        if _CARDINAL_UNIT_TAIL_RE.match(text, end) is not None:
            continue
        head = text[max(0, start - _CARDINAL_NEIGHBOUR_CHARS) : start]
        if _CARDINAL_HEAD_RE.search(head) is not None:
            continue
        normalisation = normalise_number(str(CARDINAL_WORDS[raw.lower()]), locale)
        if not normalisation.ok:  # pragma: no cover - table holds plain integers
            continue
        out.append(
            _Candidate(start, end, FactKind.NUMBER, normalisation.with_attrs(numeral="word"))
        )
    return out


def _cardinal_neighbour_blocks(text: str, start: int, end: int) -> bool:
    """Whether the words either side of a cardinal make it unreadable alone.

    Two cardinals in a row, or a cardinal joined to one by "and"/"y", is a
    compound this extractor does not build ("twenty three", "treinta y dos").
    A scale word or a fraction/ordinal tail changes the value outright
    ("three hundred", "two thirds").  Both cases are dropped.

    Scale words and tails are only checked *after* the cardinal, which is the
    only side they attach on.  An ordinal *before* it is ordinary English:
    "the first three years" is the count three.
    """
    before = _ALPHA_TOKEN_RE.findall(text[max(0, start - _CARDINAL_NEIGHBOUR_CHARS) : start])
    after = _ALPHA_TOKEN_RE.findall(text[end : end + _CARDINAL_NEIGHBOUR_CHARS])
    previous = [token.lower() for token in before[-2:]]
    following = [token.lower() for token in after[:2]]
    if previous and previous[-1] in CARDINAL_WORDS:
        return True
    if following and (
        following[0] in CARDINAL_WORDS or following[0] in CARDINAL_BLOCKING_NEIGHBOURS
    ):
        return True
    if (
        len(previous) == 2
        and previous[-1] in _CARDINAL_COORDINATORS
        and previous[0] in CARDINAL_WORDS
    ):
        return True
    return (
        len(following) == 2
        and following[0] in _CARDINAL_COORDINATORS
        and following[1] in CARDINAL_WORDS
    )


# ---------------------------------------------------------------------------
# DATE
# ---------------------------------------------------------------------------

_DATE_RE: Final[re.Pattern[str]] = re.compile(DATE_PATTERN, re.IGNORECASE)
_YEAR_RE: Final[re.Pattern[str]] = re.compile(r"\b\d{4}\b")
_RISKY_MONTHS: Final[frozenset[str]] = frozenset(
    {
        "may",
        "mar",
        "ago",
        "set",
        "abr",
        "sep",
        "oct",
        "nov",
        "dic",
        "ene",
        "feb",
        "jun",
        "jul",
        "jan",
        "apr",
        "aug",
        "dec",
    }
)


def _plausible_month_date(raw: str) -> bool:
    """Reject "may 5 people" while keeping "May 5", "3 May 2026", "3 de mayo".

    A month word that is also an ordinary word (``may``, ``mar``, ``ago``,
    ``set``) only counts as a month when it is capitalised, carries a four
    digit year, or sits in the Spanish ``N de MONTH`` frame.
    """
    lowered = raw.lower()
    month_token = ""
    for token in re.findall(r"[^\W\d_]+", raw, flags=re.UNICODE):
        if token.lower() in MONTHS:
            month_token = token
            break
    if month_token == "":
        return True
    if month_token.lower() not in _RISKY_MONTHS:
        return True
    if month_token[0].isupper():
        return True
    if _YEAR_RE.search(raw) is not None:
        return True
    return " de " in lowered


def _dates(text: str, locale: LocaleProfile) -> list[_Candidate]:
    out: list[_Candidate] = []
    for match in _DATE_RE.finditer(text):
        raw = match.group(0)
        if not _plausible_month_date(raw):
            continue
        normalisation = normalise_date(raw, locale)
        if not normalisation.ok:
            continue
        out.append(_Candidate(match.start(), match.end(), FactKind.DATE, normalisation))
    return out


# ---------------------------------------------------------------------------
# DURATION
# ---------------------------------------------------------------------------

_DURATION_RE: Final[re.Pattern[str]] = re.compile(DURATION_PATTERN, re.IGNORECASE)


def _durations(text: str, locale: LocaleProfile) -> list[_Candidate]:
    out: list[_Candidate] = []
    for match in _DURATION_RE.finditer(text):
        normalisation = normalise_duration(match.group(0), locale)
        if not normalisation.ok:
            continue
        out.append(_Candidate(match.start(), match.end(), FactKind.DURATION, normalisation))
    return out


# ---------------------------------------------------------------------------
# DEADLINE
# ---------------------------------------------------------------------------

_ANCHOR_TAIL: Final[str] = (
    r"(?P<anchor>\s+(?:of|after|from|following|starting|as\s+from|desde|"
    r"tras|a\s+partir\s+de|contados?\s+desde)\b[^.;\n]{0,60})?"
)
_PERIOD_ALT: Final[str] = (
    r"quarter|month|year|week|business\s+day|working\s+day|day|"
    r"trimestre|semestre|mes|a[nñ]o|semana|d[íi]a\s+h[áa]bil|d[íi]a"
)

_DEADLINE_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "within_duration",
        re.compile(
            rf"\bwithin\s+(?:the\s+next\s+)?(?P<dur>{DURATION_PATTERN}){_ANCHOR_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "no_later_than_duration",
        re.compile(
            rf"\b(?:no|not)\s+later\s+than\s+(?P<dur>{DURATION_PATTERN}){_ANCHOR_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "no_later_than_date",
        re.compile(
            rf"\b(?:no|not)\s+later\s+than\s+(?:the\s+)?(?P<date>{DATE_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        "end_of_period",
        re.compile(
            r"\bby\s+(?:the\s+)?end\s+of\s+(?:the\s+)?(?P<rel>current\s+|next\s+|"
            rf"this\s+|following\s+)?(?P<period>{_PERIOD_ALT})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "before_date",
        re.compile(
            r"\b(?:by|before|prior\s+to|on\s+or\s+before|not\s+after|at\s+the\s+latest\s+on)"
            rf"\s+(?:the\s+)?(?P<date>{DATE_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    # A source states the end of a period rather than an instruction to act by
    # it: "the period ends on 2026-08-22". That is the same measurement as the
    # answer's "by 2026-08-22" and it has to be extracted as one, or the two
    # end up in different kinds and the wrong evidence span gets reported.
    (
        "terminal_date",
        re.compile(
            r"\b(?:ends?|ending|expires?|expiring|lapses?|(?:is|are)\s+due)"
            rf"\s+(?:on\s+)?(?:the\s+)?(?P<date>{DATE_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        "es_terminal_date",
        re.compile(
            r"\b(?:finaliza|finalizar[áa]|termina|terminar[áa]|vence|vencer[áa]|"
            rf"expira|expirar[áa])\s+(?:el\s+)?(?P<date>{DATE_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        "es_plazo_duration",
        re.compile(
            r"\b(?:en\s+un\s+plazo\s+de|en\s+el\s+plazo\s+de|dentro\s+de(?:\s+los)?|"
            rf"dentro\s+del)\s+(?P<dur>{DURATION_PATTERN}){_ANCHOR_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "es_a_mas_tardar",
        re.compile(
            r"\b(?:a\s+m[áa]s\s+tardar|no\s+m[áa]s\s+tarde\s+d?e?l?|antes\s+del?|"
            rf"con\s+fecha\s+l[íi]mite)\s+(?:el\s+)?(?P<date>{DATE_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        "es_fin_de_periodo",
        re.compile(
            r"\bantes\s+d(?:e|el)\s+(?:fin(?:al)?\s+d(?:e|el)\s+)(?P<rel>pr[óo]ximo\s+|"
            rf"actual\s+)?(?P<period>{_PERIOD_ALT})\b",
            re.IGNORECASE,
        ),
    ),
)

_PERIOD_KEY: Final[dict[str, str]] = {
    "quarter": "quarter",
    "trimestre": "quarter",
    "month": "month",
    "mes": "month",
    "year": "year",
    "año": "year",
    "ano": "year",
    "week": "week",
    "semana": "week",
    "day": "day",
    "día": "day",
    "dia": "day",
    "business day": "business_day",
    "working day": "business_day",
    "día hábil": "business_day",
    "dia habil": "business_day",
    "semestre": "half_year",
}
_NEXT_WORDS: Final[frozenset[str]] = frozenset({"next", "following", "próximo", "proximo"})


def _deadlines(text: str, locale: LocaleProfile, reference_date: date | None) -> list[_Candidate]:
    out: list[_Candidate] = []
    for form, pattern in _DEADLINE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            if groups.get("dur"):
                # Without an anchor a relative deadline has no due date. We do not
                # read the clock to invent one, so the expression falls through to
                # the duration extractor and is reported as a duration instead.
                if reference_date is None:
                    continue
                normalisation = _deadline_from_duration(
                    groups["dur"], groups.get("anchor"), locale, reference_date
                )
            elif groups.get("date"):
                if not _plausible_month_date(groups["date"]):
                    continue
                normalisation = normalise_date(
                    groups["date"], locale, resolve_year_from=reference_date
                )
                normalisation = normalisation.with_attrs(
                    anchor="explicit_date", due_date=normalisation.value
                )
            elif groups.get("period"):
                if reference_date is None:
                    continue
                normalisation = _deadline_from_period(
                    groups["period"], groups.get("rel"), reference_date
                )
            else:  # pragma: no cover - every pattern has one of the three
                continue
            if not normalisation.ok:
                continue
            # Every deadline records the anchor it was resolved against, even
            # an absolute one: it is what makes the resolution auditable, and
            # it is how the matcher recovers the anchor without a clock.
            # An absolute date needs no anchor, so when the caller supplied
            # none the record says so rather than naming a date we never used.
            normalisation = normalisation.with_attrs(
                deadline_form=form,
                reference_date=(
                    "unanchored" if reference_date is None else reference_date.isoformat()
                ),
            )
            out.append(_Candidate(match.start(), match.end(), FactKind.DEADLINE, normalisation))
    return out


def _deadline_from_duration(
    raw_duration: str,
    anchor: str | None,
    locale: LocaleProfile,
    reference_date: date,
) -> Normalisation:
    duration = normalise_duration(raw_duration, locale)
    if not duration.ok:
        return duration
    attrs = dict(duration.attrs)
    attrs["duration"] = duration.value
    if anchor:
        # "within 30 days of receipt" hangs off an event we cannot date.  The
        # canonical value stays the duration; inventing a date from the
        # reference date would be a fabricated deadline.
        attrs["anchor"] = "event"
        attrs["anchor_text"] = " ".join(anchor.strip().split())[:_MAX_CONDITION_CHARS]
        return Normalisation(duration.value, tuple(sorted(attrs.items())), duration.ambiguities)
    if attrs.get("day_basis") == "business":
        # Business days need a holiday calendar we do not have and must not
        # guess.  Keep the duration, say why it is unresolved.
        attrs["anchor"] = "reference_date"
        attrs["unresolved_reason"] = "business_days"
        return Normalisation(duration.value, tuple(sorted(attrs.items())), duration.ambiguities)
    due = add_duration(reference_date, duration.value)
    attrs["anchor"] = "reference_date"
    attrs["reference_date"] = reference_date.isoformat()
    if due is None:
        return Normalisation(duration.value, tuple(sorted(attrs.items())), duration.ambiguities)
    attrs["due_date"] = due.isoformat()
    return Normalisation(due.isoformat(), tuple(sorted(attrs.items())), duration.ambiguities)


def _deadline_from_period(
    period: str, relative: str | None, reference_date: date
) -> Normalisation:
    key = _PERIOD_KEY.get(" ".join(period.lower().split()))
    if key is None:
        return Normalisation("")
    step = 1 if (relative or "").strip().lower() in _NEXT_WORDS else 0
    due = _period_end(reference_date, key, step)
    if due is None:
        return Normalisation("")
    attrs = {
        "anchor": "reference_date",
        "period": key,
        "period_offset": str(step),
        "reference_date": reference_date.isoformat(),
        "due_date": due.isoformat(),
    }
    return Normalisation(due.isoformat(), tuple(sorted(attrs.items())))


def _period_end(anchor: date, key: str, step: int) -> date | None:
    from datetime import date as _date
    from datetime import timedelta as _timedelta

    if key == "quarter":
        quarter = (anchor.month - 1) // 3 + step
        year = anchor.year + quarter // 4
        month = (quarter % 4) * 3 + 3
        return _last_day_of_month(year, month)
    if key == "half_year":
        half = (anchor.month - 1) // 6 + step
        year = anchor.year + half // 2
        month = (half % 2) * 6 + 6
        return _last_day_of_month(year, month)
    if key == "month":
        month_index = anchor.year * 12 + (anchor.month - 1) + step
        return _last_day_of_month(month_index // 12, month_index % 12 + 1)
    if key == "year":
        return _date(anchor.year + step, 12, 31)
    if key == "week":
        return anchor + _timedelta(days=(6 - anchor.weekday()) + 7 * step)
    if key in {"day", "business_day"}:
        return anchor + _timedelta(days=step)
    return None


def _last_day_of_month(year: int, month: int) -> date:
    from datetime import date as _date
    from datetime import timedelta as _timedelta

    if month == 12:
        return _date(year, 12, 31)
    return _date(year, month + 1, 1) - _timedelta(days=1)


# ---------------------------------------------------------------------------
# CITATION
# ---------------------------------------------------------------------------

_CITATION_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\b(?:Reg(?:ulation)?|Directive|Reglamento|Directiva)\.?\s*"
        r"\((?:EU|EC|CE|UE)\)\s*(?:No\.?\s*)?\d+/\d+(?:/(?:EU|EC|CE|UE))?",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:Directive|Directiva)\s+\d{2,4}/\d+/(?:EU|EC|CE|UE)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:Article|Art\.?|Art[íi]culo|Section|Secci[óo]n|Sec\.?|Annex|Anexo|Recital|"
        r"Considerando|Chapter|Cap[íi]tulo|Paragraph|P[áa]rrafo|Apartado|Clause|"
        r"Cl[áa]usula|Rule|Regla|Point|Punto)\s*"
        r"(?:\d+[A-Za-z]?(?:\.\d+)*(?:\(\d+\))*(?:\([a-z]\))*|[IVXLCDM]+\b)",
        re.IGNORECASE,
    ),
    re.compile(r"§{1,2}\s*\d+[A-Za-z]?(?:\.\d+)*(?:\(\d+\))*"),
    re.compile(r"\b(?:ISO|IEC|EN|BS|DIN|UNE)\s?\d{3,5}(?:[-:]\d{1,4})*"),
    re.compile(r"\b[A-Z][A-Z0-9]{1,9}(?:/[A-Za-z0-9.\-]{1,12}){1,4}\b"),
    re.compile(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]"),
)


def _citations(text: str) -> list[_Candidate]:
    out: list[_Candidate] = []
    for pattern in _CITATION_PATTERNS:
        for match in pattern.finditer(text):
            normalisation = normalise_citation(match.group(0))
            if not normalisation.ok:
                continue
            out.append(_Candidate(match.start(), match.end(), FactKind.CITATION, normalisation))
    return out


# ---------------------------------------------------------------------------
# OBLIGATION — the polarity extractor
# ---------------------------------------------------------------------------
#
# Negation is handled by matching the negative construction as a single cue,
# never as "positive modal" plus a later negation pass.  "must not" is its own
# lexical entry with polarity MUST_NOT; there is no code path in which a
# MUST_NOT is produced by inverting a MUST, so there is no code path in which a
# missed inversion silently reports the opposite of the source.
#
# Where the frozen Polarity enum cannot express a form ("should not"), the
# polarity stays SHOULD and the sense is carried in attrs["direction"] and in
# the normalised value ("should:negative").  Promoting it to MUST_NOT would
# overstate a recommendation as a prohibition.

_CUE_RES: Final[tuple[tuple[re.Pattern[str], Polarity, str, bool], ...]] = tuple(
    (re.compile(source, re.IGNORECASE), Polarity(polarity), form, weak)
    for source, polarity, form, weak in DEONTIC_CUES
)
_CONDITIONAL_RES: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(source, re.IGNORECASE), name) for source, name in CONDITIONAL_MARKERS
)
_HEDGE_RES: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(source, re.IGNORECASE), name) for source, name in SCOPE_HEDGES
)
_DOUBLE_NEG_RES: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(source, re.IGNORECASE) for source in DOUBLE_NEGATION_HEADS
)

_SENTENCE_END: Final[str] = ".;!?\n\r"
_ABBREVIATIONS: Final[frozenset[str]] = frozenset(
    {
        "art",
        "arts",
        "reg",
        "sec",
        "no",
        "nos",
        "e.g",
        "i.e",
        "cf",
        "etc",
        "vs",
        "para",
        "pp",
        "ch",
        "fig",
        "vol",
        "ed",
        "al",
        "inc",
        "ltd",
        "plc",
        "sa",
        "artículo",
        "aprox",
        "núm",
        "num",
    }
)
_CLAUSE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(
    r",\s+(?:and|or|but|y|o|pero)\s+", re.IGNORECASE
)
_WORD_RE: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]{3,}|\d+", re.UNICODE)


def _obligations(
    text: str, blocked: tuple[tuple[int, int], ...], cfg: ExtractConfig
) -> list[Fact]:
    matches: list[tuple[int, int, Polarity, str, bool]] = []
    for pattern, polarity, form, weak in _CUE_RES:
        if weak and not cfg.weak_cues:
            continue
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), polarity, form, weak))

    # Leftmost-longest, then lexicon order (already the tuple order).
    order = {form: index for index, (_, _, form, _) in enumerate(DEONTIC_CUES)}
    matches.sort(key=lambda m: (m[0], -(m[1] - m[0]), order[m[3]]))

    blocked_sorted = sorted(blocked)
    facts: list[Fact] = []
    furthest_end = 0
    for start, end, polarity, form, weak in matches:
        if start < furthest_end:
            continue
        # The site is claimed by the most specific cue that reaches it, whether
        # or not a fact comes out.  Without this, a "may not" whose clause is
        # elliptical ("...; the agent may not.") would be discarded and the
        # bare "may" underneath it would report a PERMISSION for a prohibition.
        furthest_end = end
        if _inside(start, end, blocked_sorted):
            # "May 2026" is a date, not a permission.
            continue
        fact = _obligation_fact(text, start, end, polarity, form, weak, cfg)
        if fact is None:
            continue
        facts.append(fact)
    return facts


def _inside(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """Whether ``[start, end)`` sits inside one of the sorted ``spans``."""
    position = bisect_right(spans, (start, end)) - 1
    while position >= 0 and spans[position][0] >= start - _MAX_CLAUSE_CHARS:
        if spans[position][0] <= start and end <= spans[position][1]:
            return True
        position -= 1
    return False


def _obligation_fact(
    text: str,
    cue_start: int,
    cue_end: int,
    polarity: Polarity,
    form: str,
    weak: bool,
    cfg: ExtractConfig,
) -> Fact | None:
    clause_start, clause_end = _clause_bounds(text, cue_start, cue_end)
    governed = text[cue_end:clause_end].strip()
    if len(governed) < cfg.obligation_min_clause_chars:
        return None

    negative = form in NEGATIVE_FORMS
    attrs: dict[str, str] = {
        "polarity": polarity.value,
        "operator": " ".join(text[cue_start:cue_end].split()),
        "operator_form": form,
        "operator_span": f"{cue_start}:{cue_end}",
        "governed_span": f"{cue_end}:{clause_end}",
        "predicate_key": _key_tokens(governed),
    }
    if negative:
        attrs["direction"] = "negative"
    if weak:
        attrs["cue_strength"] = "weak"

    subject = text[clause_start:cue_start].strip(" ,;:-")
    if subject:
        # Display only.  Never matched on — see the module docstring.
        attrs["subject_text"] = subject[:_MAX_CONDITION_CHARS]

    condition = _conditional(text, clause_start, clause_end, cue_start, cue_end)
    if condition is not None:
        attrs.update(condition)

    if text[clause_end : clause_end + 1] == "?":
        # A question about a duty is not a statement of one.
        attrs["scope_uncertain"] = "true"
        attrs["scope_reason"] = "interrogative"

    hedge = _scope_hedge(text, clause_start, cue_start)
    if hedge is not None:
        attrs["scope_uncertain"] = "true"
        attrs["scope_reason"] = hedge
    elif polarity in {Polarity.MUST_NOT, Polarity.NEED_NOT} and _double_negation(governed):
        attrs["scope_uncertain"] = "true"
        attrs["scope_reason"] = "double_negation"

    normalised = f"{polarity.value}:negative" if negative else polarity.value
    return Fact(
        kind=FactKind.OBLIGATION,
        raw=text[clause_start:clause_end],
        span=(clause_start, clause_end),
        normalised=normalised,
        attrs=tuple(sorted(attrs.items())),
    )


def _clause_bounds(text: str, cue_start: int, cue_end: int) -> tuple[int, int]:
    """Return the char span of the clause the operator governs.

    Bounded by sentence punctuation and by a coordinating boundary (", and ").
    A conditional antecedent is *kept inside* the clause; dropping "if X," and
    reporting a bare "you must Y" would turn a conditional duty into an
    unconditional one.
    """
    floor = max(0, cue_start - _MAX_CLAUSE_CHARS)
    start = floor
    for index in range(cue_start - 1, floor - 1, -1):
        if _is_sentence_break(text, index):
            start = index + 1
            break
    split = None
    for match in _CLAUSE_SPLIT_RE.finditer(text, start, cue_start):
        split = match.end()
    if split is not None:
        start = split
    while start < cue_start and (text[start].isspace() or text[start] in "-•*•"):
        start += 1

    ceiling = min(len(text), cue_end + _MAX_CLAUSE_CHARS)
    end = ceiling
    for index in range(cue_end, ceiling):
        if _is_sentence_break(text, index):
            end = index
            break
    while end > cue_end and text[end - 1].isspace():
        end -= 1
    return start, end


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Char span of the sentence containing ``[start, end)``."""
    floor = max(0, start - _MAX_CLAUSE_CHARS)
    left = floor
    for index in range(start - 1, floor - 1, -1):
        if _is_sentence_break(text, index):
            left = index + 1
            break
    ceiling = min(len(text), end + _MAX_CLAUSE_CHARS)
    right = ceiling
    for index in range(end, ceiling):
        if _is_sentence_break(text, index):
            right = index
            break
    return left, right


def _is_sentence_break(text: str, index: int) -> bool:
    char = text[index]
    if char not in _SENTENCE_END:
        return False
    if char in "\n\r;!?":
        return True
    # A full stop only ends a sentence when what follows is whitespace or the
    # end of the text ("4.2", "1.000" and "e.g." are not sentence ends) and the
    # word before it is not a known abbreviation.
    if index + 1 < len(text) and not text[index + 1].isspace():
        return False
    tail = re.search(r"[^\W\d_]+$", text[max(0, index - 12) : index], re.UNICODE)
    return not (tail is not None and tail.group(0).lower() in _ABBREVIATIONS)


def _conditional(
    text: str, clause_start: int, clause_end: int, cue_start: int, cue_end: int
) -> dict[str, str] | None:
    """Find the conditional that governs this obligation, if there is one.

    Looked for before the operator first ("if X, you must Y"), then after it
    ("you must Y unless Z").  The antecedent is recorded verbatim rather than
    interpreted: a checker that drops the condition reports an unconditional
    duty the source never states.
    """
    before = _earliest_marker(text[clause_start:cue_start])
    if before is not None:
        offset, name = before
        start = clause_start + offset
        # The antecedent ends at the comma that separates it from the main
        # clause, when there is one: "If the account is closed, the provider
        # must ..." conditions on the closure, not on the provider.
        stop = text.rfind(",", start, cue_start)
        stop = stop if stop > start else cue_start
        antecedent = text[start:stop].strip(" ,;:")
        if antecedent:
            return {
                "conditional": "true",
                "condition_kind": name,
                "condition_position": "before",
                "condition": " ".join(antecedent.split())[:_MAX_CONDITION_CHARS],
                "condition_span": f"{start}:{stop}",
            }

    after = _earliest_marker(text[cue_end:clause_end])
    if after is None:
        return None
    offset, name = after
    start = cue_end + offset
    stop = clause_end
    prefix = text[cue_end:start].rstrip()
    if prefix.endswith(","):
        # Parenthetical condition: "must, unless the customer objects, publish".
        comma = text.find(",", start, clause_end)
        stop = comma if comma != -1 else clause_end
    consequent = text[start:stop].strip(" ,;:")
    if not consequent:
        return None
    return {
        "conditional": "true",
        "condition_kind": name,
        "condition_position": "after",
        "condition": " ".join(consequent.split())[:_MAX_CONDITION_CHARS],
        "condition_span": f"{start}:{stop}",
    }


def _earliest_marker(window: str) -> tuple[int, str] | None:
    """Leftmost conditional marker in ``window``; ties go to lexicon order."""
    best: tuple[int, int, str] | None = None
    for index, (pattern, name) in enumerate(_CONDITIONAL_RES):
        match = pattern.search(window)
        if match is None:
            continue
        if best is None or (match.start(), index) < (best[0], best[1]):
            best = (match.start(), index, name)
    if best is None:
        return None
    return best[0], best[2]


def _scope_hedge(text: str, clause_start: int, cue_start: int) -> str | None:
    window = text[clause_start:cue_start]
    for pattern, name in _HEDGE_RES:
        if pattern.search(window) is not None:
            return name
    return None


def _double_negation(governed: str) -> bool:
    head = governed[:48]
    return any(pattern.search(head) is not None for pattern in _DOUBLE_NEG_RES)


def _key_tokens(clause: str) -> str:
    """Content-word signature of a clause, used only to align two obligations.

    Sorted and de-duplicated so it is stable, capped so a runaway clause cannot
    dominate a similarity score.
    """
    tokens = [
        token.lower() for token in _WORD_RE.findall(clause) if token.lower() not in STOPWORDS
    ]
    unique = sorted(set(tokens))
    return " ".join(unique[:_MAX_KEY_TOKENS])
