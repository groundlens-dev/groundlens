"""Numerals, decided by arithmetic.

A number is not similar to another number. It is equal or it is wrong. This
module is the whole reason the library exists, so it is deliberately the
strictest thing in it:

* values are :class:`~decimal.Decimal`, never float, inside a fixed context, so
  an unrelated library cannot change our answers by touching the global one;
* the reading of an ambiguous numeral is never guessed. ``1.234`` is 1234 in
  Spain and 1.234 in the US. When the locale is unknown, *both* readings are
  returned and the caller matches against the best of them -- abstaining would
  silently drop a word from the floor and inflate it, which is worse;
* the locale comes from an argument. Never from ``LC_ALL``. A library whose
  answers depend on the shell that launched it is not reproducible.

Only ``decimal``, ``re`` and ``typing`` are imported. That is enforced in CI by
a job that installs pytest and nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation

#: Fixed arithmetic context. Not the thread-local one -- see module docstring.
CTX = Context(prec=34)

#: Three digits is the only tail length compatible with a grouping separator:
#: "1.234" could be 1234 or 1.234, but "1.23" can only be a decimal.
GROUP_SIZE = 3
#: Two digits is the minimum for a numeral to be treated as a fact. A bare
#: single digit is overwhelmingly a list enumerator or a section number.
MIN_DIGITS = 2
#: An ambiguous numeral has exactly two valid readings: grouped and fractional.
BOTH_READINGS = 2

AMBIGUITY_CODES = frozenset({"grouping_vs_decimal", "separator_repeated", "grouping_malformed"})

_GROUP_SPACE = "    "
_MINUS = "-−–"
_CURRENCY = "$€£¥₹"

#: Digit-group repetition is bounded at 8 on purpose. An unbounded ``+`` here
#: backtracks quadratically on adversarial model output, and this library reads
#: untrusted text by definition.
NUMBER_PATTERN = re.compile(
    r"""
    (?P<open>\()?
    (?P<sign>[-−–+])?
    (?:(?P<cur>[$€£¥₹])\s?)?
    (?P<body>
        \d{1,3}(?:[    ]\d{3}){1,8}(?!\d)(?:[.,]\d{1,9})?
      | \d{1,3}(?:['’]\d{3}){1,8}(?!\d)(?:[.,]\d{1,9})?
      | \d{1,3}(?:[.,]\d{3}){1,8}(?!\d)(?:[.,]\d{1,9})?
      | \d+(?:[.,]\d{1,9})?
    )
    (?!\d)
    (?P<pct>\s?%)?
    (?P<close>\))?
    """,
    re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class LocaleProfile:
    """How this corpus writes numbers. ``und`` means unknown -- keep both readings."""

    name: str
    decimal_sep: str | None
    group_sep: str | None

    @property
    def known(self) -> bool:
        return self.decimal_sep is not None


LOCALES: dict[str, LocaleProfile] = {
    "und": LocaleProfile("und", None, None),
    "en": LocaleProfile("en", ".", ","),
    "es": LocaleProfile("es", ",", "."),
    "de": LocaleProfile("de", ",", "."),
    "fr": LocaleProfile("fr", ",", " "),
    "it": LocaleProfile("it", ",", "."),
    "pt": LocaleProfile("pt", ",", "."),
    "nl": LocaleProfile("nl", ",", "."),
    "ch": LocaleProfile("ch", ".", "'"),
}


def locale(name: str) -> LocaleProfile:
    try:
        return LOCALES[name.lower()]
    except KeyError as exc:  # pragma: no cover - argument validation
        raise ValueError(f"unknown locale {name!r}; known: {sorted(LOCALES)}") from exc


@dataclass(frozen=True, slots=True)
class Numeral:
    """A numeral found in text, with every value it could legitimately denote."""

    text: str
    span: tuple[int, int]
    readings: tuple[Decimal, ...]
    notes: tuple[str, ...] = ()

    @property
    def ambiguous(self) -> bool:
        return len(self.readings) > 1

    @property
    def canonical(self) -> str:
        return " | ".join(format_decimal(r) for r in self.readings)


def format_decimal(value: Decimal) -> str:
    """Canonical string for a value. ``1000``, ``1000.5`` -- never ``1E+3``."""
    normal = value.normalize(CTX)
    exponent = normal.as_tuple().exponent
    if isinstance(exponent, int) and exponent > 0:
        normal = normal.quantize(Decimal(1), context=CTX)
    return format(normal, "f")


def _to_decimal(digits: str) -> Decimal | None:
    try:
        return CTX.create_decimal(digits)
    except (InvalidOperation, ValueError):
        return None


def _readings(body: str, profile: LocaleProfile) -> tuple[tuple[Decimal, ...], tuple[str, ...]]:
    """Every value ``body`` could denote, plus why there is more than one."""
    for space in _GROUP_SPACE:
        body = body.replace(space, "")
    body = body.replace("'", "").replace("’", "")
    seps = [c for c in body if c in ".,"]

    if not seps:
        value = _to_decimal(body)
        return ((value,) if value is not None else (), ())

    if profile.known:
        assert profile.decimal_sep is not None
        stripped = body.replace(profile.group_sep or "\x00", "")
        value = _to_decimal(stripped.replace(profile.decimal_sep, "."))
        return ((value,) if value is not None else (), ())

    distinct = set(seps)
    if len(distinct) == MIN_DIGITS:  # both separators present
        # Both separators present: the last one is the decimal point.
        dec = body[max(body.rfind("."), body.rfind(","))]
        grp = "." if dec == "," else ","
        value = _to_decimal(body.replace(grp, "").replace(dec, "."))
        return ((value,) if value is not None else (), ())

    sep = seps[0]
    tail = body.rsplit(sep, 1)[1]
    if len(seps) > 1:
        # 1.234.567 -- repeated separator can only be grouping.
        value = _to_decimal(body.replace(sep, ""))
        return ((value,) if value is not None else (), ("separator_repeated",))
    if len(tail) != GROUP_SIZE:
        # 1.5 or 1.23456 -- three digits is the only grouping-compatible length.
        value = _to_decimal(body.replace(sep, "."))
        return ((value,) if value is not None else (), ())

    grouped = _to_decimal(body.replace(sep, ""))
    fractional = _to_decimal(body.replace(sep, "."))
    values = tuple(v for v in (grouped, fractional) if v is not None)
    if len(values) < BOTH_READINGS:
        return (values, ("grouping_malformed",))
    return (values, ("grouping_vs_decimal",))


def find_numerals(text: str, profile: LocaleProfile) -> list[Numeral]:
    """Every numeral in ``text``, with spans into ``text`` and all valid readings.

    Bare single digits are skipped: they are overwhelmingly list enumerators and
    section numbers, and treating them as facts produces false alarms that cost
    more than the defects they catch.
    """
    found: list[Numeral] = []
    for match in NUMBER_PATTERN.finditer(text):
        body = match.group("body")
        if len(re.sub(r"\D", "", body)) < MIN_DIGITS:
            continue
        readings, notes = _readings(body, profile)
        if not readings:
            continue
        negative = bool(match.group("sign") and match.group("sign")[0] in _MINUS) or bool(
            match.group("open") and match.group("close")
        )
        if negative:
            readings = tuple(-r for r in readings)
        # A sign only binds when it touches a currency symbol or a digit:
        # "-$101,755" is negative, "payment - $101,755" is a punctuation dash
        # and stays positive, and the 7 in "pages 5 - 7" is not minus seven.
        # The pattern still tolerates a space after a currency symbol
        # ("$ 5,428", common in PDF extraction), so the raw match can carry
        # whitespace at either end. A span
        # that includes it would make every reported source slice wrong by a
        # character, so trim it here rather than at each call site.
        raw = match.group(0)
        start, end = match.span()
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw) - len(raw.rstrip())
        found.append(
            Numeral(
                text=raw.strip(),
                span=(start + lead, end - trail),
                readings=readings,
                notes=notes,
            )
        )
    return found


def value_set(texts: list[str], profile: LocaleProfile) -> frozenset[Decimal]:
    """Every value the sources could be asserting. The answer is checked against this."""
    values: set[Decimal] = set()
    for text in texts:
        for numeral in find_numerals(text, profile):
            values.update(numeral.readings)
    return frozenset(values)


def matches(numeral: Numeral, values: frozenset[Decimal]) -> bool:
    """True if any legitimate reading of ``numeral`` appears in the sources.

    Exact equality on Decimal. No tolerance. A tolerance parameter is the first
    step towards a threshold, and thresholds are what this library refuses to ship.
    """
    return any(reading in values for reading in numeral.readings)
