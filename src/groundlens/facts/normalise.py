"""Canonical string forms for extracted values.

This module is the value normaliser and it is deliberately a **separate unit**
from the extractor and the matcher: it takes a raw substring plus a
:class:`~groundlens.determinism.LocaleProfile` and returns a canonical string.
It never touches the input text as a whole, never looks at the environment and
never returns a ``float``.  Every numeric quantity is a :class:`decimal.Decimal`
internally and a string on the way out.

Design rules, in order of importance:

1. **No float, ever.**  ``float("0.1")`` is not ``1/10`` and an audit record that
   contains one is not reproducible across platforms.  Arithmetic runs inside a
   fixed :class:`decimal.Context` so the result cannot depend on an ambient
   context set by unrelated code.
2. **Ambiguity is surfaced, never guessed.**  When the locale profile cannot
   decide a reading, the ambiguity code is returned alongside the value.  The
   caller records it in ``Fact.attrs`` and the matcher may downgrade the fact to
   ``UNCHECKABLE`` rather than emit a confident wrong answer.
3. **No environment locale.**  Decimal separator, group separator and date order
   come from the profile only.  ``locale``/``LC_ALL``/``LANG`` are never read.

Canonical forms produced here:

============  ================================  ==========================
kind          canonical form                    example
============  ================================  ==========================
number        plain decimal string              ``"1000"``, ``"-3.25"``
currency      ``"<CODE> <amount>"``             ``"EUR 1000"``
percent       ``"<amount>%"`` / ``"<amount>pp"``  ``"12.5%"``
date          ISO 8601, ``"--MM-DD"`` if no year  ``"2026-03-03"``
duration      ISO 8601 duration                 ``"P30D"``, ``"PT24H"``
citation      upper-cased canonical reference   ``"ARTICLE 12"``
============  ================================  ==========================
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Context, Decimal, InvalidOperation, localcontext
from typing import TYPE_CHECKING, Final

from groundlens.facts.lexicon import (
    AMBIGUOUS_MARKERS,
    AMBIGUOUS_MULTIPLIERS,
    BUSINESS_DAY_QUALIFIERS,
    CALENDAR_DAY_QUALIFIERS,
    CURRENCY_CODES,
    CURRENCY_SYMBOLS,
    CURRENCY_WORDS,
    DURATION_UNITS,
    MONTHS,
    MULTIPLIERS,
    POSTFIX_DAY_QUALIFIERS,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from groundlens.determinism import LocaleProfile

__all__ = [
    "AMBIGUITY_CODES",
    "NUMBER_PATTERN",
    "Normalisation",
    "add_duration",
    "date_order_of",
    "decimal_separator_of",
    "format_decimal",
    "group_separator_of",
    "normalise_citation",
    "normalise_currency",
    "normalise_date",
    "normalise_duration",
    "normalise_number",
    "normalise_percent",
    "parse_locale_decimal",
]

# A fixed context: the result must not depend on whatever precision some other
# library left in the thread-local decimal context.
_CTX: Final[Context] = Context(prec=34)

NUMBER_PATTERN: Final[str] = (
    r"(?:(?<![^\s(\[])[-\u2212])?"
    r"(?:\d{1,3}(?:[.,\u2019' ]\d{3}){1,8}(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
)
"""Digit-group aware numeric token.  Grouped forms are listed first on purpose.

The group repetition is bounded at eight (up to 10**27) rather than left open.
An unbounded ``+`` here backtracks quadratically across a long run of separated
digit triples, which is a denial-of-service shape in a library that reads
untrusted model output.  No quantity in scope needs more groups than that."""

_NUMBER_RE: Final[re.Pattern[str]] = re.compile(NUMBER_PATTERN)

AMBIGUITY_CODES: Final[tuple[str, ...]] = (
    "currency_symbol_ambiguous",
    "currency_word_ambiguous",
    "date_order_ambiguous",
    "grouping_malformed",
    "grouping_vs_decimal",
    "invalid_date",
    "multiplier_ambiguous",
    "separator_repeated",
    "two_digit_year",
    "unparsable",
    "year_inferred",
)
"""Every ambiguity code this module can emit.  Additive only."""

_SIGN_CHARS: Final[str] = "-\u2212"
_SPACE_CHARS: Final[str] = " \u00a0\u202f\u2009\u2007"
_GROUPING_CHARS: Final[str] = ".,\u2019'" + _SPACE_CHARS

# Currencies whose minor unit is not 1/100.  Used only to decide whether a
# three-digit "fraction" is a plausible reading or a foreign thousands group.
_MINOR_UNITS: Final[dict[str, int]] = {
    "JPY": 0,
    "KRW": 0,
    "CLP": 0,
    "VND": 0,
    "ISK": 0,
    "HUF": 0,
}


@dataclass(frozen=True, slots=True)
class Normalisation:
    """The result of normalising one raw substring.

    Attributes:
        value: The canonical string form, or ``""`` when the input could not be
            normalised at all.  Never a float, never locale dependent.
        attrs: Sorted key/value pairs of string metadata, ready to be merged
            into :attr:`groundlens.types.Fact.attrs`.
        ambiguities: Sorted ambiguity codes drawn from :data:`AMBIGUITY_CODES`.
            A non-empty tuple means the reading depended on a rule the profile
            could not fully settle.
    """

    value: str
    attrs: tuple[tuple[str, str], ...] = ()
    ambiguities: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether a canonical value was produced."""
        return self.value != ""

    def with_attrs(self, **extra: str) -> Normalisation:
        """Return a copy with ``extra`` merged into :attr:`attrs` (sorted)."""
        merged = dict(self.attrs)
        merged.update(extra)
        return Normalisation(
            value=self.value,
            attrs=tuple(sorted(merged.items())),
            ambiguities=self.ambiguities,
        )


def _make(
    value: str,
    attrs: dict[str, str] | None = None,
    ambiguities: tuple[str, ...] = (),
) -> Normalisation:
    return Normalisation(
        value=value,
        attrs=tuple(sorted((attrs or {}).items())),
        ambiguities=tuple(sorted(set(ambiguities))),
    )


# ---------------------------------------------------------------------------
# Locale profile accessors
# ---------------------------------------------------------------------------
#
# ``LocaleProfile`` is owned by groundlens.determinism (contract section 5).
# This module reads three properties off it and nothing else.  The alias lists
# exist so a field rename on the other side degrades to a documented default
# instead of an AttributeError at extraction time.

_DECIMAL_ALIASES: Final[tuple[str, ...]] = (
    "decimal_separator",
    "decimal_sep",
    "decimal_point",
    "decimal",
)
_GROUP_ALIASES: Final[tuple[str, ...]] = (
    "group_separator",
    "thousands_separator",
    "thousands_sep",
    "grouping_separator",
    "group_sep",
    "thousands",
)
_DATE_ORDER_ALIASES: Final[tuple[str, ...]] = ("date_order", "date_format", "day_order")
_CURRENCY_ALIASES: Final[tuple[str, ...]] = ("currency", "default_currency", "currency_code")
_NAME_ALIASES: Final[tuple[str, ...]] = ("name", "id", "profile", "locale_profile")


def _first_attr(profile: object, names: tuple[str, ...]) -> str | None:
    for name in names:
        value = getattr(profile, name, None)
        if isinstance(value, str) and value != "":
            return value
    return None


def decimal_separator_of(profile: LocaleProfile) -> str:
    """Return the profile's decimal separator, defaulting to ``"."``."""
    return _first_attr(profile, _DECIMAL_ALIASES) or "."


def group_separator_of(profile: LocaleProfile) -> str:
    """Return the profile's digit-group separator, defaulting to ``","``."""
    found = _first_attr(profile, _GROUP_ALIASES)
    if found is None:
        return "," if decimal_separator_of(profile) == "." else "."
    return found


def date_order_of(profile: LocaleProfile) -> str:
    """Return the profile's date order as one of ``"DMY"``, ``"MDY"``, ``"YMD"``."""
    raw = _first_attr(profile, _DATE_ORDER_ALIASES) or "DMY"
    token = re.sub(r"[^A-Za-z]", "", raw).upper()
    if set(token) == {"D", "M", "Y"} and len(token) == 3:
        return token
    return "DMY"


def currency_of(profile: LocaleProfile) -> str | None:
    """Return the profile's default ISO 4217 code, if it declares one."""
    found = _first_attr(profile, _CURRENCY_ALIASES)
    if found is not None and found.upper() in CURRENCY_CODES:
        return found.upper()
    return None


def profile_name_of(profile: LocaleProfile) -> str:
    """Return the profile's name, for the record.  ``"unknown"`` if it has none."""
    return _first_attr(profile, _NAME_ALIASES) or "unknown"


# ---------------------------------------------------------------------------
# Decimal handling
# ---------------------------------------------------------------------------


def format_decimal(value: Decimal) -> str:
    """Render ``value`` as a canonical plain decimal string.

    No exponent notation, no trailing fractional zeros, no negative zero.

    Args:
        value: The quantity to render.

    Returns:
        A canonical string such as ``"1000"``, ``"-3.25"`` or ``"0"``.
    """
    with localcontext(_CTX):
        text = f"{value:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text.startswith("-") and set(text[1:]) <= {"0", "."}:
        text = "0"
    return text or "0"


def _digits_only(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def parse_locale_decimal(
    raw: str,
    profile: LocaleProfile,
    *,
    max_fraction_digits: int | None = None,
) -> tuple[Decimal | None, tuple[str, ...]]:
    """Parse a locale-formatted numeric token into a :class:`~decimal.Decimal`.

    The separator reading comes from the profile.  Where the profile alone
    cannot settle it, a documented rule is applied and an ambiguity code is
    returned so the caller can record that it was not certain.

    Args:
        raw: The numeric token, e.g. ``"1 000,00"``.  Currency symbols and unit
            words must already be stripped.
        profile: Locale profile supplying the separators.
        max_fraction_digits: If given, a literal reading producing more
            fractional digits than this is treated as implausible and the token
            is re-read with the separator as a digit group.  Used for currency,
            where a three-digit "fraction" on a two-decimal currency is almost
            always a foreign thousands group.

    Returns:
        ``(value, ambiguities)``.  ``value`` is ``None`` when the token could
        not be parsed at all.
    """
    ambiguities: list[str] = []
    text = raw.strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    while text and text[0] in _SIGN_CHARS + "+":
        negative = negative or text[0] in _SIGN_CHARS
        text = text[1:].strip()

    for space in _SPACE_CHARS[1:]:
        text = text.replace(space, " ")
    core = "".join(ch for ch in text if ch.isdigit() or ch in _GROUPING_CHARS).strip()
    if not any(ch.isdigit() for ch in core):
        return None, ("unparsable",)

    seps = [(i, ch) for i, ch in enumerate(core) if not ch.isdigit()]
    if not seps:
        return _signed(Decimal(core), negative), ()

    dec_sep = decimal_separator_of(profile)
    last_index, last_char = seps[-1]
    digits_after_last = len(_digits_only(core[last_index + 1 :]))
    digits_before_last = len(_digits_only(core[:last_index]))
    distinct = {ch for _, ch in seps}

    decimal_at: int | None = None
    if last_char in {".", ","}:
        if digits_after_last != 3:
            decimal_at = last_index
        elif len(seps) >= 2:
            # Several separators and a trailing three-digit run: the last one is
            # a decimal point only if it is the profile's decimal separator and
            # differs from the others (e.g. "1.000,000" under eu-es).
            if last_char == dec_sep and distinct != {last_char}:
                decimal_at = last_index
        elif last_char == dec_sep and (
            digits_before_last > 3 or core[:last_index].lstrip("0") != core[:last_index]
        ):
            # "1234,567" or "0,500": a group separator cannot sit there.
            decimal_at = last_index
        elif last_char == dec_sep:
            # Genuinely ambiguous: "1,000" under a comma-decimal profile.
            decimal_at = last_index
            ambiguities.append("grouping_vs_decimal")

    if decimal_at is not None and any(ch == core[decimal_at] for i, ch in seps if i != decimal_at):
        ambiguities.append("separator_repeated")

    if decimal_at is not None:
        int_text, frac_digits = core[:decimal_at], _digits_only(core[decimal_at + 1 :])
        if (
            max_fraction_digits is not None
            and len(frac_digits) == 3
            and len(frac_digits) > max_fraction_digits
            and 1 <= len(_digits_only(int_text)) <= 3
            and int_text.lstrip("0") == int_text
        ):
            # Implausible fraction for this unit: re-read the separator as a
            # foreign thousands group.  "1,000 EUR" is one thousand euro, not
            # one euro stated to a tenth of a cent.
            if "grouping_vs_decimal" not in ambiguities:
                ambiguities.append("grouping_vs_decimal")
            decimal_at, int_text, frac_digits = None, core, ""
    else:
        int_text, frac_digits = core, ""

    if not _groups_well_formed(int_text):
        ambiguities.append("grouping_malformed")

    literal = _digits_only(int_text) or "0"
    if frac_digits:
        literal = f"{literal}.{frac_digits}"
    try:
        with localcontext(_CTX):
            value = Decimal(literal)
    except InvalidOperation:  # pragma: no cover - guarded by the digit check
        return None, ("unparsable",)
    return _signed(value, negative), tuple(sorted(set(ambiguities)))


def _signed(value: Decimal, negative: bool) -> Decimal:
    with localcontext(_CTX):
        return -value if negative else value


def _groups_well_formed(int_text: str) -> bool:
    """Whether ``int_text`` splits into a lead group plus exact 3-digit groups."""
    parts = re.split(r"[^0-9]", int_text)
    parts = [p for p in parts if p != ""]
    if len(parts) <= 1:
        return True
    return len(parts[0]) <= 3 and all(len(p) == 3 for p in parts[1:])


# ---------------------------------------------------------------------------
# NUMBER
# ---------------------------------------------------------------------------


def normalise_number(
    raw: str,
    profile: LocaleProfile,
    *,
    multiplier: str | None = None,
) -> Normalisation:
    """Normalise a bare number.

    Args:
        raw: The raw numeric token exactly as it appears in the text.
        profile: Locale profile supplying separators.
        multiplier: Optional scale word already isolated by the extractor
            (``"million"``, ``"mil"``, ...).

    Returns:
        A :class:`Normalisation` whose value is a plain decimal string.
    """
    value, ambiguities = parse_locale_decimal(raw, profile)
    if value is None:
        return _make("", {}, ambiguities or ("unparsable",))
    attrs: dict[str, str] = {}
    if multiplier is not None:
        value, mult_ambiguities, applied = _apply_multiplier(value, multiplier)
        ambiguities = tuple(sorted(set(ambiguities) | set(mult_ambiguities)))
        if applied is not None:
            attrs["multiplier"] = applied
    return _make(format_decimal(value), attrs, ambiguities)


def _apply_multiplier(value: Decimal, token: str) -> tuple[Decimal, tuple[str, ...], str | None]:
    key = token.strip().lower().rstrip(".")
    if key in AMBIGUOUS_MULTIPLIERS:
        with localcontext(_CTX):
            return value * Decimal("1000000000000"), ("multiplier_ambiguous",), key
    factor = MULTIPLIERS.get(key)
    if factor is None:
        return value, (), None
    with localcontext(_CTX):
        return value * Decimal(factor), (), key


# ---------------------------------------------------------------------------
# CURRENCY
# ---------------------------------------------------------------------------


def resolve_currency(token: str, profile: LocaleProfile) -> tuple[str, tuple[str, ...]]:
    """Resolve a currency symbol, code or word to an ISO 4217 code.

    Args:
        token: The currency marker as written, e.g. ``"€"``, ``"EUR"``, ``"$"``.
        profile: Locale profile, consulted only for its declared currency.

    Returns:
        ``(code, ambiguities)``.  When the marker cannot be resolved the token
        itself is returned upper-cased and an ambiguity code is set, so the
        matcher can require a literal symbol match instead of guessing.
    """
    cleaned = token.strip().rstrip(".")
    upper = cleaned.upper()
    lower = cleaned.lower()
    if upper in CURRENCY_CODES:
        return upper, ()
    if cleaned in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[cleaned], ()
    family = AMBIGUOUS_MARKERS.get(cleaned) or AMBIGUOUS_MARKERS.get(lower)
    if family is not None:
        declared = currency_of(profile)
        if declared is not None and declared in family:
            return declared, ()
        code = "currency_word_ambiguous" if cleaned[:1].isalpha() else "currency_symbol_ambiguous"
        return cleaned.upper(), (code,)
    if lower in CURRENCY_WORDS:
        return CURRENCY_WORDS[lower], ()
    return upper, ("currency_symbol_ambiguous",)


def normalise_currency(
    raw_amount: str,
    currency_token: str,
    profile: LocaleProfile,
    *,
    multiplier: str | None = None,
) -> Normalisation:
    """Normalise a monetary amount to ``"<CODE> <amount>"``.

    Args:
        raw_amount: The numeric token, without the currency marker.
        currency_token: The currency symbol, code or word as written.
        profile: Locale profile.
        multiplier: Optional scale word (``"million"``, ``"millones"``, ...).

    Returns:
        A :class:`Normalisation`; ``attrs`` always carries ``currency`` and the
        raw ``currency_symbol``.
    """
    code, code_ambiguities = resolve_currency(currency_token, profile)
    minor = _MINOR_UNITS.get(code, 2)
    value, num_ambiguities = parse_locale_decimal(raw_amount, profile, max_fraction_digits=minor)
    ambiguities = tuple(sorted(set(code_ambiguities) | set(num_ambiguities)))
    if value is None:
        return _make("", {"currency": code}, ambiguities or ("unparsable",))
    attrs = {"currency": code, "currency_symbol": currency_token.strip()}
    if multiplier is not None:
        value, mult_ambiguities, applied = _apply_multiplier(value, multiplier)
        ambiguities = tuple(sorted(set(ambiguities) | set(mult_ambiguities)))
        if applied is not None:
            attrs["multiplier"] = applied
    return _make(f"{code} {format_decimal(value)}", attrs, ambiguities)


# ---------------------------------------------------------------------------
# PERCENT
# ---------------------------------------------------------------------------


def normalise_percent(
    raw_amount: str,
    profile: LocaleProfile,
    *,
    percentage_points: bool = False,
) -> Normalisation:
    """Normalise a percentage.

    Percentage *points* are kept distinct from percentages: "rose by 2 points"
    and "rose by 2%" are different claims and collapsing them creates a silent
    false match.

    Args:
        raw_amount: The numeric token without the ``%`` sign.
        profile: Locale profile.
        percentage_points: Whether the unit was percentage points.

    Returns:
        A :class:`Normalisation` with value ``"12.5%"`` or ``"2pp"``.
    """
    value, ambiguities = parse_locale_decimal(raw_amount, profile)
    if value is None:
        return _make("", {}, ambiguities or ("unparsable",))
    unit = "pp" if percentage_points else "%"
    return _make(
        f"{format_decimal(value)}{unit}",
        {"unit": "percentage_point" if percentage_points else "percent"},
        ambiguities,
    )


# ---------------------------------------------------------------------------
# DATE
# ---------------------------------------------------------------------------

_ISO_DATE_RE: Final[re.Pattern[str]] = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_NUMERIC_DATE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(\d{1,4})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2,4})$"
)
_MONTH_ALT: Final[str] = "|".join(sorted(MONTHS, key=len, reverse=True))
_DMY_TEXT_RE: Final[re.Pattern[str]] = re.compile(
    rf"^(\d{{1,2}})(?:º|st|nd|rd|th)?\s+(?:de\s+)?({_MONTH_ALT})\.?"
    rf"(?:\s*(?:,|de|del)?\s*(\d{{4}}))?$",
    re.IGNORECASE,
)
_MDY_TEXT_RE: Final[re.Pattern[str]] = re.compile(
    rf"^({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{{4}}))?$",
    re.IGNORECASE,
)
_MONTH_YEAR_RE: Final[re.Pattern[str]] = re.compile(
    rf"^(?:de\s+)?({_MONTH_ALT})\.?\s+(?:de\s+|del\s+)?(\d{{4}})$", re.IGNORECASE
)

DATE_PATTERN: Final[str] = (
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{2,4}"
    rf"|\d{{1,2}}(?:º|st|nd|rd|th)?\s+(?:de\s+)?(?:{_MONTH_ALT})"
    r"(?:\.(?=\s*(?:,|de|del)?\s*\d{4}))?"
    r"(?:\s*(?:,|de|del)?\s*\d{4})?"
    rf"|(?:{_MONTH_ALT})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s*,?\s*\d{{4}})?"
    rf"|(?:{_MONTH_ALT})\s+(?:de\s+|del\s+)?\d{{4}}"
)
"""Surface forms recognised as dates.  Used by the extractor, defined here so
the pattern and its parser cannot drift apart."""


def normalise_date(
    raw: str,
    profile: LocaleProfile,
    *,
    resolve_year_from: date | None = None,
) -> Normalisation:
    """Normalise a date expression to ISO 8601.

    Args:
        raw: The date expression as written.
        profile: Locale profile supplying ``date_order``.
        resolve_year_from: When the expression carries no year, the year is
            inferred as the next occurrence on or after this date and
            ``year_inferred`` is recorded.  When ``None``, the value is the
            year-less ISO form ``"--MM-DD"``.

    Returns:
        A :class:`Normalisation` with an ISO date, ``"--MM-DD"``, ``"YYYY-MM"``
        or ``""`` when the expression is not a valid date.
    """
    text = " ".join(raw.strip().rstrip(".,;").split())
    attrs: dict[str, str] = {}
    ambiguities: list[str] = []

    iso = _ISO_DATE_RE.match(text)
    if iso is not None:
        return _build_date(int(iso[1]), int(iso[2]), int(iso[3]), attrs, ambiguities)

    numeric = _NUMERIC_DATE_RE.match(text)
    if numeric is not None:
        return _numeric_date(numeric, profile, resolve_year_from)

    dmy = _DMY_TEXT_RE.match(text)
    if dmy is not None:
        month = MONTHS[dmy[2].lower()]
        return _textual_date(int(dmy[1]), month, dmy[3], resolve_year_from)

    mdy = _MDY_TEXT_RE.match(text)
    if mdy is not None:
        month = MONTHS[mdy[1].lower()]
        return _textual_date(int(mdy[2]), month, mdy[3], resolve_year_from)

    month_year = _MONTH_YEAR_RE.match(text)
    if month_year is not None:
        month = MONTHS[month_year[1].lower()]
        return _make(f"{int(month_year[2]):04d}-{month:02d}", {"precision": "month"}, ())

    return _make("", {}, ("unparsable",))


def _numeric_date(
    match: re.Match[str],
    profile: LocaleProfile,
    resolve_year_from: date | None,
) -> Normalisation:
    a, b, c = match[1], match[2], match[3]
    attrs: dict[str, str] = {}
    ambiguities: list[str] = []
    order = date_order_of(profile)

    if len(a) == 4:
        year, month, day = int(a), int(b), int(c)
    else:
        first, second = int(a), int(b)
        year = _expand_year(c, ambiguities, attrs, resolve_year_from)
        if order == "MDY":
            month, day = first, second
        else:
            day, month = first, second
        if first <= 12 and second <= 12 and first != second:
            ambiguities.append("date_order_ambiguous")
            attrs["date_order"] = order
            attrs["date_ambiguous"] = "true"
    return _build_date(year, month, day, attrs, ambiguities)


def _expand_year(
    token: str,
    ambiguities: list[str],
    attrs: dict[str, str],
    resolve_year_from: date | None,
) -> int:
    if len(token) == 4:
        return int(token)
    value = int(token)
    ambiguities.append("two_digit_year")
    attrs["two_digit_year"] = "true"
    century = 2000 if value < 70 else 1900
    if resolve_year_from is not None:
        attrs["century_window"] = "1970-2069"
    return century + value


def _textual_date(
    day: int, month: int, year_token: str | None, resolve_year_from: date | None
) -> Normalisation:
    attrs: dict[str, str] = {}
    ambiguities: list[str] = []
    if year_token is not None:
        return _build_date(int(year_token), month, day, attrs, ambiguities)
    if resolve_year_from is None:
        try:
            date(2000, month, day)
        except ValueError:
            return _make("", {}, ("invalid_date",))
        return _make(f"--{month:02d}-{day:02d}", {"precision": "month_day"}, ())
    year = resolve_year_from.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return _make("", {}, ("invalid_date",))
    if candidate < resolve_year_from:
        year += 1
    attrs["year_inferred"] = "true"
    ambiguities.append("year_inferred")
    return _build_date(year, month, day, attrs, ambiguities)


def _build_date(
    year: int,
    month: int,
    day: int,
    attrs: dict[str, str],
    ambiguities: list[str],
) -> Normalisation:
    try:
        value = date(year, month, day)
    except ValueError:
        return _make("", attrs, (*ambiguities, "invalid_date"))
    return _make(value.isoformat(), attrs, tuple(ambiguities))


# ---------------------------------------------------------------------------
# DURATION
# ---------------------------------------------------------------------------

_UNIT_ALT: Final[str] = "|".join(sorted(DURATION_UNITS, key=len, reverse=True))
_QUALIFIER_ALT: Final[str] = "|".join(
    sorted(
        (*BUSINESS_DAY_QUALIFIERS, *CALENDAR_DAY_QUALIFIERS),
        key=len,
        reverse=True,
    )
)
_POSTFIX_ALT: Final[str] = "|".join(sorted(POSTFIX_DAY_QUALIFIERS, key=len, reverse=True))
_TERM: Final[str] = (
    rf"(?:{NUMBER_PATTERN})\s*(?:(?:{_QUALIFIER_ALT})\s+)?(?:{_UNIT_ALT})\b"
    rf"(?:\s+(?:{_POSTFIX_ALT})\b)?"
)

DURATION_PATTERN: Final[str] = rf"{_TERM}(?:\s*(?:,|and|y)\s*{_TERM}){{0,2}}"
"""Surface forms recognised as durations, including ``1 year and 6 months``.

The qualifier may precede the unit (English "30 business days") or follow it
(Spanish "30 días hábiles")."""

_DURATION_TERM_RE: Final[re.Pattern[str]] = re.compile(
    rf"({NUMBER_PATTERN})\s*(?:({_QUALIFIER_ALT})\s+)?({_UNIT_ALT})\b"
    rf"(?:\s+({_POSTFIX_ALT})\b)?",
    re.IGNORECASE,
)

_ISO_ORDER: Final[tuple[tuple[str, str], ...]] = (
    ("Y", "Y"),
    ("M", "M"),
    ("D", "D"),
    ("H", "H"),
    ("M_T", "M"),
    ("S", "S"),
)


def normalise_duration(raw: str, profile: LocaleProfile) -> Normalisation:
    """Normalise a duration to an ISO 8601 duration string.

    Weeks and fortnights are converted to days (exact); quarters to months.
    Months and years are never converted to days — their length is not fixed and
    a converted value would match things it should not.

    Args:
        raw: The duration as written, e.g. ``"30 business days"``.
        profile: Locale profile supplying separators for the count.

    Returns:
        A :class:`Normalisation` with value ``"P30D"``, ``"PT24H"``, ... and
        ``day_basis`` in ``attrs`` when the days were qualified.
    """
    totals: dict[str, Decimal] = {}
    attrs: dict[str, str] = {}
    ambiguities: list[str] = []
    found = False

    for term in _DURATION_TERM_RE.finditer(raw):
        count, term_ambiguities = parse_locale_decimal(term[1], profile)
        if count is None:
            ambiguities.extend(term_ambiguities or ("unparsable",))
            continue
        ambiguities.extend(term_ambiguities)
        unit = DURATION_UNITS[_fold(term[3])]
        qualifier = _fold(term[2] or term[4]) if (term[2] or term[4]) else None
        if qualifier is not None and unit == "D":
            if qualifier in BUSINESS_DAY_QUALIFIERS:
                attrs["day_basis"] = "business"
            elif qualifier in CALENDAR_DAY_QUALIFIERS:
                attrs["day_basis"] = "calendar"
        with localcontext(_CTX):
            if unit == "W":
                unit, count = "D", count * 7
            elif unit == "FORTNIGHT":
                unit, count = "D", count * 14
            elif unit == "Q":
                unit, count = "M", count * 3
            totals[unit] = totals.get(unit, Decimal(0)) + count
        found = True

    if not found:
        return _make("", attrs, tuple(ambiguities) or ("unparsable",))

    date_part = "".join(
        f"{format_decimal(totals[key])}{letter}" for key, letter in _ISO_ORDER[:3] if key in totals
    )
    time_part = "".join(
        f"{format_decimal(totals[key])}{letter}" for key, letter in _ISO_ORDER[3:] if key in totals
    )
    value = f"P{date_part}" + (f"T{time_part}" if time_part else "")
    if value == "P":
        value = "P0D"
    return _make(value, attrs, tuple(ambiguities))


def _fold(text: str) -> str:
    return text.strip().lower()


_ISO_DURATION_RE: Final[re.Pattern[str]] = re.compile(
    r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$"
)


def add_duration(start: date, iso_duration: str) -> date | None:
    """Add an ISO 8601 duration to ``start``.

    Only whole calendar arithmetic is performed.  Sub-day components are
    ignored for the purpose of a due *date*.

    Args:
        start: The anchor date.
        iso_duration: A duration produced by :func:`normalise_duration`.

    Returns:
        The resulting date, or ``None`` when the duration cannot be applied.
    """
    match = _ISO_DURATION_RE.match(iso_duration)
    if match is None:
        return None
    years = int(match[1] or 0)
    months = int(match[2] or 0)
    days = int(match[3] or 0)
    total_months = start.year * 12 + (start.month - 1) + years * 12 + months
    year, month = divmod(total_months, 12)
    month += 1
    day = min(start.day, _days_in_month(year, month))
    try:
        anchored = date(year, month, day)
    except ValueError:  # pragma: no cover - guarded by _days_in_month
        return None
    return anchored + timedelta(days=days)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


# ---------------------------------------------------------------------------
# CITATION
# ---------------------------------------------------------------------------

_CITATION_TOKEN_MAP: Final[dict[str, str]] = {
    "art": "ARTICLE",
    "art.": "ARTICLE",
    "article": "ARTICLE",
    "articulo": "ARTICLE",
    "artículo": "ARTICLE",
    "arts": "ARTICLES",
    "sec": "SECTION",
    "sec.": "SECTION",
    "section": "SECTION",
    "seccion": "SECTION",
    "sección": "SECTION",
    "§": "SECTION",
    "§§": "SECTIONS",
    "reg": "REGULATION",
    "reg.": "REGULATION",
    "regulation": "REGULATION",
    "reglamento": "REGULATION",
    "directive": "DIRECTIVE",
    "directiva": "DIRECTIVE",
    "annex": "ANNEX",
    "anexo": "ANNEX",
    "recital": "RECITAL",
    "considerando": "RECITAL",
    "chapter": "CHAPTER",
    "capitulo": "CHAPTER",
    "capítulo": "CHAPTER",
    "paragraph": "PARAGRAPH",
    "para": "PARAGRAPH",
    "para.": "PARAGRAPH",
    "parrafo": "PARAGRAPH",
    "párrafo": "PARAGRAPH",
    "apartado": "PARAGRAPH",
    "point": "POINT",
    "punto": "POINT",
    "clause": "CLAUSE",
    "clausula": "CLAUSE",
    "cláusula": "CLAUSE",
    "rule": "RULE",
    "regla": "RULE",
    # Union spellings collapse so a Spanish citation matches an English one.
    "(ue)": "(EU)",
    "(eu)": "(EU)",
    "(ce)": "(EC)",
    "(ec)": "(EC)",
}


def normalise_citation(raw: str) -> Normalisation:
    """Normalise a legal or bibliographic reference to a canonical string.

    Cross-language synonyms collapse to one English token, so a Spanish answer
    citing ``artículo 12`` matches English evidence citing ``Article 12``.

    Args:
        raw: The reference as written.

    Returns:
        A :class:`Normalisation` with an upper-cased canonical reference.
    """
    text = " ".join(raw.strip().split())
    bracketed = re.fullmatch(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]", text)
    if bracketed is not None:
        numbers = [n.strip() for n in bracketed[1].split(",")]
        return _make(f"REF {','.join(numbers)}", {"citation_style": "bracketed"}, ())

    text = re.sub(r"§\s*", "§ ", text)
    tokens = [t for t in re.split(r"\s+", text) if t]
    out: list[str] = []
    for token in tokens:
        key = token.lower().rstrip(",;")
        mapped = _CITATION_TOKEN_MAP.get(key) or _CITATION_TOKEN_MAP.get(key.rstrip("."))
        out.append(mapped if mapped is not None else token.upper().rstrip(",;"))
    value = " ".join(out)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        return _make("", {}, ("unparsable",))
    return _make(value, {}, ())
