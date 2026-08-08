r"""Shared determinism primitives for the groundlens v2 control path.

Every module in the control path depends on this one. Read it before
writing anything that touches text, numbers, dates or serialisation.

The seven determinism rules (verbatim from the frozen v2 interface
contract, section 5, binding on every agent):

1. **No floating point in the decision path or anywhere in the audit
   record.** Comparisons are on normalised strings and integer counts.
   Tolerances are declared as decimal strings and compared with
   ``decimal.Decimal``.
2. **NFKC once, on input, before extraction.** All spans are offsets
   into the NFKC-normalised text. Never into the raw input.
3. **No locale from the environment.** Decimal separator, thousands
   separator and date order come from the pack's ``locale_profile``.
   Reading ``LC_ALL``, ``LANG`` or calling ``locale.setlocale`` is
   forbidden.
4. **No wall clock.** Relative dates resolve against ``reference_date``,
   which the caller passes. ``date.today()`` and ``datetime.now()`` are
   forbidden in the deterministic path. The timestamp belongs in the
   ``AuditLog`` row, not in the record.
5. **Sort at every serialisation boundary.** No ``set`` iteration order
   and no incidental ``dict`` order in output. ``findings`` sorted by
   ``(code, span or (-1,-1), rule_id or "")``. ``evidence`` sorted by
   ``id``. ``attrs`` sorted by key.
6. **Stdlib ``re`` only.** Any other regex engine must be pinned and its
   version recorded.
7. **No randomness, no hashing of object ids, no ``PYTHONHASHSEED``
   dependence.**

Rules 1, 2, 3, 5 and 7 are enforced mechanically by the suite in
``tests/determinism/``, which also runs as a hard binary CI gate across
the whole supported Python matrix on two operating systems.

Whitespace policy for :func:`normalise_text`
--------------------------------------------
Compatibility normalisation alone is not enough to make character
offsets reproducible, because the same document arrives with CRLF from
one pipeline and LF from another, and with trailing spaces that a copy
step introduced. :func:`normalise_text` therefore applies, in this
order and exactly once:

1. Removal of four invisible characters that carry no meaning and are a
   known evasion vector for value matching: SOFT HYPHEN (U+00AD), ZERO
   WIDTH SPACE (U+200B), WORD JOINER (U+2060) and ZERO WIDTH NO-BREAK
   SPACE / BOM (U+FEFF). Zero-width joiner and non-joiner are *not*
   removed, because they are meaningful in Arabic and Indic scripts.
2. One and only one call to ``unicodedata.normalize("NFKC", ...)``.
3. Whitespace-run collapsing: every maximal run of whitespace becomes a
   single LINE FEED if the run contains at least one line break
   (``\n``, ``\r``, ``\x0b``, ``\x0c``, ``\x1c``-``\x1e``,
   ``\u0085``, ``\u2028``, ``\u2029``), and a single SPACE otherwise.
4. Stripping of leading and trailing whitespace.

The function is idempotent: ``normalise_text(normalise_text(s)) ==
normalise_text(s)`` for every input. Callers compute spans against the
returned string and never against the raw input.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from groundlens.types import Finding

__all__ = [
    "DATE_ORDERS",
    "LOCALE_PROFILES",
    "UNICODE_FORM",
    "LocaleProfile",
    "canonical_decimal_str",
    "get_locale_profile",
    "normalise_text",
    "parse_decimal",
    "sort_attrs",
    "sort_evidence",
    "sort_findings",
]

# ── Text normalisation ──────────────────────────────────────────────────────


UNICODE_FORM: Final = "NFKC"
"""The one normalisation form used everywhere. Recorded in the audit record."""


_INVISIBLE_CODEPOINTS: Final[tuple[int, ...]] = (
    0x00AD,  # SOFT HYPHEN
    0x200B,  # ZERO WIDTH SPACE
    0x2060,  # WORD JOINER
    0xFEFF,  # ZERO WIDTH NO-BREAK SPACE (byte order mark)
)
"""Zero-width and soft-hyphen codepoints removed before normalisation."""

_INVISIBLE_TABLE: Final[dict[int, None]] = dict.fromkeys(_INVISIBLE_CODEPOINTS, None)

_LINE_BREAKS: Final[frozenset[str]] = frozenset("\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")
"""Characters that count as a line break for the whitespace policy."""

_WHITESPACE_RUN: Final[re.Pattern[str]] = re.compile(r"\s+")
r"""Stdlib ``re`` only (rule 6). ``\s`` on ``str`` is Unicode-aware."""


def _collapse(match: re.Match[str]) -> str:
    """Return the replacement for one whitespace run."""
    run = match.group(0)
    return "\n" if any(ch in _LINE_BREAKS for ch in run) else " "


def normalise_text(s: str) -> str:
    r"""Normalise text once, deterministically, for span-stable extraction.

    See the module docstring for the exact whitespace policy. The result
    is the *only* string that spans may index into: a :class:`~groundlens
    .types.Fact` span is a pair of character offsets into the value this
    function returns, never into the caller's raw input.

    Args:
        s: Raw input text, in any encoding-normalised Python ``str`` form.

    Returns:
        The normalised text. Idempotent, locale-independent, and stable
        across Python versions for every character assigned before
        Unicode 13 (the Unicode normalisation stability policy
        guarantees NFKC mappings never change once a character ships).

    Example:
        >>> normalise_text("  \u3000 x \r\n\n  1\u00a0234  ")
        'x\n1 234'
    """
    stripped = s.translate(_INVISIBLE_TABLE)
    normalised = unicodedata.normalize(UNICODE_FORM, stripped)
    collapsed = _WHITESPACE_RUN.sub(_collapse, normalised)
    return collapsed.strip(" \n")


# ── Locale profiles ─────────────────────────────────────────────────────────


DATE_ORDERS: Final[frozenset[str]] = frozenset({"dmy", "mdy", "ymd"})
"""The only permitted values of :attr:`LocaleProfile.date_order`."""


@dataclass(frozen=True, slots=True)
class LocaleProfile:
    """How to read numbers and dates, declared by the pack, never by the host.

    Rule 3 forbids reading locale from the environment. A pack declares
    ``locale_profile: <name>`` and every parse in that run uses the
    profile looked up here. Two hosts with different ``LC_ALL`` settings
    produce byte-identical audit records.

    Attributes:
        name: Stable profile identifier, recorded in the audit record.
        decimal_separator: The single character separating the integer
            and fractional parts, e.g. ``","`` for ``eu-es``.
        thousands_separator: The grouping character, or ``""`` when the
            profile recognises no grouping at all.
        date_order: One of ``"dmy"``, ``"mdy"``, ``"ymd"``.
    """

    name: str
    decimal_separator: str
    thousands_separator: str
    date_order: str

    def __post_init__(self) -> None:
        """Reject profiles that cannot parse unambiguously."""
        if len(self.decimal_separator) != 1:
            msg = (
                f"decimal_separator must be exactly one character, got {self.decimal_separator!r}"
            )
            raise ValueError(msg)
        if len(self.thousands_separator) > 1:
            msg = (
                "thousands_separator must be one character or empty, "
                f"got {self.thousands_separator!r}"
            )
            raise ValueError(msg)
        if self.decimal_separator == self.thousands_separator:
            msg = "decimal_separator and thousands_separator must differ"
            raise ValueError(msg)
        if self.date_order not in DATE_ORDERS:
            msg = f"date_order must be one of {sorted(DATE_ORDERS)}, got {self.date_order!r}"
            raise ValueError(msg)


_BUILTIN_PROFILES: Final[tuple[LocaleProfile, ...]] = (
    LocaleProfile(name="eu-es", decimal_separator=",", thousands_separator=".", date_order="dmy"),
    LocaleProfile(name="eu-de", decimal_separator=",", thousands_separator=".", date_order="dmy"),
    LocaleProfile(name="eu-fr", decimal_separator=",", thousands_separator=" ", date_order="dmy"),
    LocaleProfile(name="en-gb", decimal_separator=".", thousands_separator=",", date_order="dmy"),
    LocaleProfile(name="en-us", decimal_separator=".", thousands_separator=",", date_order="mdy"),
    LocaleProfile(name="iso", decimal_separator=".", thousands_separator="", date_order="ymd"),
)

LOCALE_PROFILES: Final[Mapping[str, LocaleProfile]] = MappingProxyType(
    {profile.name: profile for profile in _BUILTIN_PROFILES}
)
"""The built-in profile table. Read-only; packs reference entries by name."""


def get_locale_profile(name: str) -> LocaleProfile:
    """Look up a built-in locale profile by name.

    Args:
        name: A key of :data:`LOCALE_PROFILES`, e.g. ``"eu-es"``.

    Returns:
        The matching :class:`LocaleProfile`.

    Raises:
        KeyError: If the name is not a built-in profile. Packs must not
            invent profiles inline; an unknown name is a pack error and
            fails closed rather than falling back to a default.
    """
    try:
        return LOCALE_PROFILES[name]
    except KeyError:
        msg = f"unknown locale_profile {name!r}; known profiles: {sorted(LOCALE_PROFILES)}"
        raise KeyError(msg) from None


# ── Decimal parsing ─────────────────────────────────────────────────────────


_SIGN_CHARS: Final[str] = "+-\u2212\u2012\u2013\u2014"
"""ASCII plus/minus and the Unicode minus and dash characters treated as sign."""

_STRIP_CHARS: Final[str] = "%\u2030"
"""Percent and per-mille, stripped so callers never write their own parser."""

_DIGITS: Final[re.Pattern[str]] = re.compile(r"\A[0-9]+\Z")


def parse_decimal(raw: str, profile: LocaleProfile) -> Decimal:
    """Parse a number from text under an explicit locale profile.

    This is the only sanctioned number parser in the codebase. ``float()``
    is forbidden everywhere (rule 1) and the determinism suite scans the
    source tree for it.

    Grouping is validated, not merely stripped: under ``eu-es`` the text
    ``"1.234"`` parses as ``1234`` and ``"1.23"`` raises, because a
    two-digit group is not a legal thousands group. That turns a silent
    thousandfold locale error into a loud one.

    Args:
        raw: The number as it appears in the text. Currency symbols,
            percent and per-mille signs, and surrounding whitespace are
            stripped. A leading or trailing sign is honoured, as is the
            accounting convention ``"(1.234,56)"`` for a negative value.
        profile: The profile supplying the separators. Never inferred.

    Returns:
        The exact value as a :class:`decimal.Decimal`. The fractional
        digits present in the input are preserved, so ``"1,50"`` under
        ``eu-es`` returns ``Decimal("1.50")`` and not ``Decimal("1.5")``.

    Raises:
        ValueError: If the text is not a number under this profile, has
            more than one decimal separator, or has illegal grouping.

    Example:
        >>> parse_decimal("1.234,56 €", get_locale_profile("eu-es"))
        Decimal('1234.56')
        >>> parse_decimal("1,234.56", get_locale_profile("en-us"))
        Decimal('1234.56')
    """
    text = normalise_text(raw)
    text = "".join(
        ch for ch in text if ch not in _STRIP_CHARS and unicodedata.category(ch) != "Sc"
    )
    if profile.thousands_separator == " ":
        # The separator is itself whitespace, so only the outer whitespace goes.
        text = text.strip()
    else:
        text = "".join(ch for ch in text if not ch.isspace())

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    while text and text[0] in _SIGN_CHARS:
        negative ^= text[0] != "+"
        text = text[1:]
    while text and text[-1] in _SIGN_CHARS:
        negative ^= text[-1] != "+"
        text = text[:-1]

    if not text:
        msg = f"not a number under profile {profile.name!r}: {raw!r}"
        raise ValueError(msg)

    integer, fraction = _split_on_decimal_separator(text, profile, raw)
    integer = _validate_grouping(integer, profile, raw)

    if not _DIGITS.match(integer) or (fraction != "" and not _DIGITS.match(fraction)):
        msg = f"not a number under profile {profile.name!r}: {raw!r}"
        raise ValueError(msg)

    canonical = f"{'-' if negative else ''}{integer}" + (f".{fraction}" if fraction else "")
    try:
        return Decimal(canonical)
    except InvalidOperation:  # pragma: no cover - guarded by the checks above
        msg = f"not a number under profile {profile.name!r}: {raw!r}"
        raise ValueError(msg) from None


def _split_on_decimal_separator(text: str, profile: LocaleProfile, raw: str) -> tuple[str, str]:
    """Split into integer and fractional digit strings. Empty fraction if none."""
    count = text.count(profile.decimal_separator)
    if count > 1:
        msg = f"more than one decimal separator under profile {profile.name!r}: {raw!r}"
        raise ValueError(msg)
    if count == 0:
        return text, ""
    integer, _, fraction = text.partition(profile.decimal_separator)
    if fraction == "":
        msg = f"trailing decimal separator under profile {profile.name!r}: {raw!r}"
        raise ValueError(msg)
    return (integer or "0"), fraction


def _validate_grouping(integer: str, profile: LocaleProfile, raw: str) -> str:
    """Validate thousands grouping and return the integer part without separators."""
    separator = profile.thousands_separator
    if separator == "":
        if any(not ch.isdigit() for ch in integer):
            msg = f"profile {profile.name!r} recognises no thousands separator: {raw!r}"
            raise ValueError(msg)
        return integer or "0"
    if separator not in integer:
        return integer or "0"
    groups = integer.split(separator)
    if len(groups[0]) not in (1, 2, 3) or any(len(g) != 3 for g in groups[1:]):
        msg = (
            f"illegal thousands grouping under profile {profile.name!r}: {raw!r} "
            "(groups after the first must be exactly three digits)"
        )
        raise ValueError(msg)
    return "".join(groups)


def canonical_decimal_str(value: Decimal) -> str:
    """Render a decimal as the canonical string form used in ``Fact.normalised``.

    Trailing fractional zeros are dropped, exponent notation is never
    emitted, and negative zero collapses to ``"0"``, so two values that
    compare equal always render to the same string and the string
    comparison in the matcher agrees with the numeric one.

    Args:
        value: The value to render.

    Returns:
        A plain decimal string, e.g. ``"1234.56"``, ``"100"``, ``"0"``.
    """
    if value == 0:
        return "0"
    normalised = value.normalize()
    return format(normalised, "f")


# ── Sorting at serialisation boundaries (rule 5) ────────────────────────────


_NO_SPAN: Final[tuple[int, int]] = (-1, -1)
"""The sort-key stand-in for a finding that has no span."""


def sort_findings(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    """Sort findings into the one order the contract permits.

    The key is ``(code, span or (-1, -1), rule_id or "")``, where the
    span is the span of the finding's fact. Findings without a fact sort
    before findings with one, because ``(-1, -1)`` precedes every real
    span.

    Args:
        findings: Findings in any order, including ``set`` iteration order.

    Returns:
        A tuple in canonical order. Stable, so equal keys keep their
        relative input order.
    """

    def key(finding: Finding) -> tuple[str, tuple[int, int], str]:
        span = finding.fact.span if finding.fact is not None else _NO_SPAN
        return (finding.code, span, finding.rule_id or "")

    return tuple(sorted(findings, key=key))


def sort_evidence(items: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """Sort ``(id, value)`` evidence pairs by id, as rule 5 requires.

    Args:
        items: Pairs in any order.

    Returns:
        A tuple sorted by the first element.
    """
    return tuple(sorted(items, key=lambda pair: pair[0]))


def sort_attrs(attrs: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """Sort fact attributes by key, then by value, as rule 5 requires.

    Args:
        attrs: Key/value pairs with string values only.

    Returns:
        A tuple sorted by ``(key, value)``.
    """
    return tuple(sorted(attrs))
