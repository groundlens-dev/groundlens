"""Obligation strength: one canonical form, one ordering, one comparison.

The extractor writes a polarity into two places.  ``Fact.normalised`` carries
the *decorated* form, which is the enum value plus an optional ``:negative``
suffix for the recommendations the frozen :class:`~groundlens.types.Polarity`
enum cannot spell ("should not" is ``should:negative``, because promoting it to
``MUST_NOT`` would turn a recommendation into a prohibition).  ``attrs`` carries
the bare enum value under ``polarity``.

Two consumers read those values: the matcher, which decides whether the answer
and the evidence say the same thing, and the ``obligation_polarity_consistent``
assertion, which decides whether the answer says something *firmer* than the
evidence.  Before this module existed each consumer did its own string handling
at its own comparison site, and a value that one of them produced was not
necessarily a value the other could read.  That is how the wedge check came to
be silently degrading to UNCHECKABLE.

So: every polarity string, wherever it came from, goes through
:func:`canonical_polarity` before anything is decided about it, and the
strength ordering exists exactly once, in :data:`POLARITY_STRENGTH`.  A string
this module cannot canonicalise yields ``None``, and ``None`` means "cannot
decide", never "no contradiction" and never "contradiction".

No floats, no locale, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from groundlens.types import Polarity

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

__all__ = [
    "NEGATIVE_SUFFIX",
    "POLARITY_STRENGTH",
    "CanonicalPolarity",
    "canonical_polarity",
    "exceeds_or_inverts",
    "polarity_strength",
]

NEGATIVE_SUFFIX: Final[str] = ":negative"
"""The one decoration ``Fact.normalised`` is allowed to carry."""

POLARITY_STRENGTH: Final[Mapping[Polarity, int]] = {
    Polarity.NEED_NOT: 0,
    Polarity.MAY: 1,
    Polarity.SHOULD: 2,
    Polarity.MUST: 3,
    Polarity.MUST_NOT: 3,
}
"""How much discretion each operator removes from the reader.

The single ordering.  Nothing else in the library may define a second one.

Obligation and prohibition sit together at the top: both leave the reader no
choice, and they differ in *direction*, not in strength.  Direction is carried
by the polarity itself, so a strength comparison alone can never tell MUST from
MUST_NOT — which is why :func:`exceeds_or_inverts` checks both.
"""


@dataclass(frozen=True, slots=True)
class CanonicalPolarity:
    """A polarity string reduced to the two things that can be compared.

    Attributes:
        polarity: The frozen enum member.
        negated: Whether the operator was a negative recommendation
            ("should not"), which the enum has no member for.
    """

    polarity: Polarity
    negated: bool = False

    @property
    def value(self) -> str:
        """The canonical string form, round-tripping :func:`canonical_polarity`."""
        return f"{self.polarity.value}{NEGATIVE_SUFFIX}" if self.negated else self.polarity.value

    @property
    def strength(self) -> int:
        """This operator's position in :data:`POLARITY_STRENGTH`."""
        return POLARITY_STRENGTH[self.polarity]

    def describe(self) -> str:
        """A plain-language reading, for finding messages.

        Findings are read by compliance reviewers, not by the people who
        wrote the enum, so ``must_not`` is never shown to a human.
        """
        if self.polarity is Polarity.SHOULD:
            return "recommended against" if self.negated else "recommended"
        return _PLAIN[self.polarity]


_PLAIN: Final[Mapping[Polarity, str]] = {
    Polarity.MUST: "required",
    Polarity.MUST_NOT: "forbidden",
    Polarity.MAY: "allowed",
    Polarity.NEED_NOT: "not required",
    Polarity.SHOULD: "recommended",
}


def canonical_polarity(value: str | None) -> CanonicalPolarity | None:
    """Reduce a polarity string to its canonical form.

    Accepts the bare enum value (``"may"``), the decorated form the extractor
    writes for negative recommendations (``"should:negative"``), and nothing
    else.  Surrounding whitespace and case are tolerated because they carry no
    meaning; anything further is refused.

    Args:
        value: A string from ``Fact.normalised``, from ``attrs["polarity"]`` or
            from ``Match.evidence_value``.  ``None`` and the empty string are
            accepted and refused.

    Returns:
        The :class:`CanonicalPolarity`, or ``None`` when the string is not one
        this library wrote.  ``None`` is the honest answer for a value we
        cannot read, and every caller must turn it into UNCHECKABLE rather than
        guessing a strength.

    Example:
        >>> canonical_polarity("should:negative").describe()
        'recommended against'
        >>> canonical_polarity("may (may)") is None
        True
    """
    if not value:
        return None
    head, separator, tail = value.strip().casefold().partition(":")
    if separator and tail != NEGATIVE_SUFFIX[1:]:
        return None
    try:
        polarity = Polarity(head)
    except ValueError:
        return None
    return CanonicalPolarity(polarity=polarity, negated=bool(separator))


def polarity_strength(value: str | None) -> int | None:
    """Return a polarity string's strength, or ``None`` if it cannot be read.

    Args:
        value: Any polarity string, decorated or not.

    Returns:
        The value from :data:`POLARITY_STRENGTH`, or ``None``.
    """
    canonical = canonical_polarity(value)
    return None if canonical is None else canonical.strength


def exceeds_or_inverts(answer: CanonicalPolarity, evidence: CanonicalPolarity) -> bool:
    """Whether the answer overstates or reverses what the evidence licenses.

    Two ways an answer can misreport a duty, and both matter:

    * **Exceeds.**  The answer removes discretion the evidence leaves — "you
      must" where the source says "you may".
    * **Inverts.**  The answer points the opposite way at the same strength —
      "you must disclose" where the source says "you must not disclose", or
      "you should" where the source says "you should not".  A strength
      comparison alone cannot see this, because MUST and MUST_NOT sit at the
      same height by design.

    An answer that is *weaker* than the evidence is not reported here.  It is
    still a difference, and the matcher still records it as CONTRADICTED; it is
    simply not what the ``obligation_polarity_consistent`` assertion is for.

    Args:
        answer: The polarity stated in the answer.
        evidence: The polarity found in the evidence.

    Returns:
        ``True`` when the answer exceeds or inverts the evidence.
    """
    if answer.strength > evidence.strength:
        return True
    return answer.strength == evidence.strength and answer != evidence
