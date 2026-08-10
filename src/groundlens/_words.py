"""Segmentation. Which units of the answer get an anchor, and which are skipped.

The library owns segmentation. It does not use the encoder's pre-tokenizer,
because encoders disagree with us on the boundaries that matter most -- a BERT
pre-tokenizer splits ``10,000`` into three tokens, which is exactly the split
that lets a wrong number hide. Words are mapped onto encoder tokens later, by
character-span overlap, in ``_align``.

Scope, stated rather than assumed: space-delimited scripts. If a large fraction
of the answer is CJK or Thai, ``str``-level segmentation produces one enormous
"word" and the score is meaningless. We emit a warning and say so, which is more
honest than a half-working ICU dependency.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from groundlens._numerals import LocaleProfile, Numeral, find_numerals

#: Function words. A wrong "the" is not a grounding defect, and leaving them in
#: means the floor is permanently occupied by innocent words -- which is exactly
#: why the pure-geometry variant of this metric measures nothing.
STOPWORDS = frozenset(
    """
a an the and or but if then else of to in on at by for with from as is are was were be been
being it its this that these those he she they we you i his her their our your not no yes do
does did done can could will would should may might must have has had about into over under
between also such more most other some any each which who whom whose when where why how than
too very just only there here what while during per via upon within without
""".split()
)

_WORD = re.compile(r"[^\W\d_](?:[\w'’\-]*[^\W_])?|[^\W\d_]", re.UNICODE)
_UNSEGMENTED = re.compile(r"[　-鿿฀-๿가-힯]")


@dataclass(frozen=True, slots=True)
class Unit:
    """One segment of the answer, before it has been scored."""

    text: str
    span: tuple[int, int]
    kind: str  # "lexical" | "numeral" | "skipped"
    numeral: Numeral | None = None
    notes: tuple[str, ...] = ()


def _is_stopword(text: str) -> bool:
    return text.casefold() in STOPWORDS


def segment(text: str, profile: LocaleProfile) -> list[Unit]:
    """Split ``text`` into scoring units, numerals first so they win overlaps.

    Numerals are claimed before words, so ``10,000`` is one unit rather than
    three, and ``30 days`` is a numeral unit plus a lexical unit.
    """
    numerals = find_numerals(text, profile)
    claimed = [False] * (len(text) + 1)
    units: list[Unit] = []

    for numeral in numerals:
        start, end = numeral.span
        units.append(
            Unit(
                text=text[start:end].strip(),
                span=(start + (len(text[start:end]) - len(text[start:end].lstrip())), end),
                kind="numeral",
                numeral=numeral,
                notes=numeral.notes,
            )
        )
        for i in range(start, end):
            claimed[i] = True

    for match in _WORD.finditer(text):
        start, end = match.span()
        if any(claimed[i] for i in range(start, end)):
            continue
        word = match.group(0)
        notes: tuple[str, ...] = ()
        kind = "lexical"
        if _is_stopword(word):
            kind, notes = "skipped", ("stopword",)
        units.append(Unit(text=word, span=(start, end), kind=kind, notes=notes))

    units.sort(key=lambda u: u.span)
    return units


def scoring_units(units: list[Unit]) -> list[Unit]:
    return [u for u in units if u.kind != "skipped"]


def segmentation_warnings(text: str) -> tuple[str, ...]:
    """Warn when whitespace segmentation is not a defensible way to read this text."""
    if not text:
        return ()
    unsegmented = len(_UNSEGMENTED.findall(text))
    if unsegmented / len(text) > 0.30:
        return (
            "answer is largely in an unsegmented script (CJK/Thai); whitespace "
            "segmentation does not apply and this score should not be relied on",
        )
    return ()


def content_word_count(text: str, profile: LocaleProfile) -> int:
    """Independent count, used by tests to assert no word is silently dropped."""
    return len(scoring_units(segment(text, profile)))


def strip_accents(text: str) -> str:
    """Only used for stopword lookup in accented locales; never for matching."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
