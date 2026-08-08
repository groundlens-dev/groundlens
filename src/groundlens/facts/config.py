"""Configuration for extraction and matching.

Both configs are frozen dataclasses that can also be built from the plain
mapping a rule pack carries under its ``facts:`` key (contract section 4).
Every threshold and tolerance is a **decimal string**; nothing here is ever a
``float``.  ``coerce`` accepts either form so a caller can pass parsed YAML
straight through without a conversion step that could silently drop a key.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Final

__all__ = [
    "DEFAULT_MAX_FACTS",
    "ExtractConfig",
    "MatchConfig",
    "as_decimal",
]

DEFAULT_MAX_FACTS: Final[int] = 512
"""Hard cap on facts returned from one document.

When the extractor hits this it truncates deterministically (document order)
and the control layer is expected to emit ``extractor.limit_exceeded``.
"""


def as_decimal(value: str | Decimal, *, default: str = "0") -> Decimal:
    """Parse a tolerance/threshold string into a :class:`~decimal.Decimal`.

    Args:
        value: A decimal string such as ``"0.01"``, or an existing Decimal.
        default: Used when ``value`` cannot be parsed.

    Returns:
        The parsed value; ``Decimal(default)`` when the input is unusable.
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return default


@dataclass(frozen=True, slots=True)
class ExtractConfig:
    """Knobs for :func:`groundlens.facts.extract.extract_facts`.

    Attributes:
        max_facts: Upper bound on returned facts; the tail is dropped in
            document order so the truncation is reproducible.
        weak_cues: Whether to emit obligations for weak deontic cues (``can``,
            ``cannot``, ``is expected to``).  These carry the extractor's
            highest false-positive rate; a pack for prose-heavy traffic should
            turn them off.
        kinds: Restrict extraction to these ``FactKind`` values (by string
            value).  Empty means all kinds.
        obligation_min_clause_chars: Clauses shorter than this after the
            operator are dropped as fragments.
    """

    max_facts: int = DEFAULT_MAX_FACTS
    weak_cues: bool = True
    kinds: frozenset[str] = frozenset()
    obligation_min_clause_chars: int = 3

    @classmethod
    def coerce(cls, config: ExtractConfig | Mapping[str, object] | None) -> ExtractConfig:
        """Build an :class:`ExtractConfig` from a mapping, or pass one through.

        Args:
            config: ``None``, an existing config, or a rule pack ``facts:``
                mapping.  Unknown keys are ignored, never an error: a pack
                written against a newer version must not crash an older
                extractor.

        Returns:
            A config instance.
        """
        if isinstance(config, cls):
            return config
        if config is None or not isinstance(config, Mapping):
            return cls()
        raw = dict(config)
        extract_section = raw.get("extract")
        if isinstance(extract_section, Mapping):
            raw = {**raw, **dict(extract_section)}
        kinds_value = raw.get("kinds")
        kinds: frozenset[str] = frozenset()
        if isinstance(kinds_value, (list, tuple, set, frozenset)):
            kinds = frozenset(str(k) for k in kinds_value)
        return cls(
            max_facts=_as_int(raw.get("max_facts"), DEFAULT_MAX_FACTS),
            weak_cues=_as_bool(raw.get("weak_cues"), True),
            kinds=kinds,
            obligation_min_clause_chars=_as_int(raw.get("obligation_min_clause_chars"), 3),
        )

    def wants(self, kind_value: str) -> bool:
        """Whether ``kind_value`` should be extracted under this config."""
        return not self.kinds or kind_value in self.kinds


@dataclass(frozen=True, slots=True)
class MatchConfig:
    """Knobs for :func:`groundlens.facts.match.match_facts`.

    All comparison thresholds are decimal strings parsed with
    :class:`~decimal.Decimal`.  ``reference_date`` lives here rather than in the
    signature because the matcher re-extracts facts from the evidence and must
    resolve relative deadlines against the same anchor the answer used.

    Attributes:
        tolerances: Per-kind absolute tolerance, as decimal strings keyed by
            ``FactKind`` value.  Default is exact comparison.
        relative_tolerances: Per-kind relative tolerance as a fraction, decimal
            string.  ``"0.01"`` means one percent of the evidence value.
        context_similarity_min: Containment score a candidate's surrounding
            words must reach before a differing value is reported as
            ``CONTRADICTED`` rather than ``UNMATCHED``.
        obligation_similarity_min: Same, for matching an obligation clause to
            its counterpart in the evidence.
        contradiction_requires_context: When false, any same-kind fact in the
            evidence with a different value contradicts.  Leave this true; the
            false-positive rate without a context gate is not shippable.
        conditional_mismatch_uncheckable: When the answer states an obligation
            unconditionally and the evidence conditions it, report
            ``UNCHECKABLE`` instead of ``MATCHED``.
        reference_date: Anchor for relative deadlines found in the evidence.
        max_evidence_chars: Evidence items longer than this are still matched,
            but only through their own extracted spans; no whole-chunk match is
            ever emitted.
    """

    tolerances: Mapping[str, str] = field(default_factory=dict)
    relative_tolerances: Mapping[str, str] = field(default_factory=dict)
    context_similarity_min: str = "0.34"
    obligation_similarity_min: str = "0.5"
    contradiction_requires_context: bool = True
    conditional_mismatch_uncheckable: bool = True
    reference_date: date | None = None
    max_evidence_chars: int = 200_000

    @classmethod
    def coerce(
        cls,
        config: MatchConfig | Mapping[str, object] | None,
        *,
        reference_date: date | None = None,
    ) -> MatchConfig:
        """Build a :class:`MatchConfig` from a rule pack ``facts:`` mapping.

        The pack form is ``{"currency": {"tolerance": "0"}, ...}``; a flat form
        with the keys of this dataclass is also accepted.

        Args:
            config: ``None``, an existing config, or a mapping.
            reference_date: Overrides the config's own reference date when set.

        Returns:
            A config instance.
        """
        if isinstance(config, cls):
            return (
                config
                if reference_date is None
                else replace(config, reference_date=reference_date)
            )
        if config is None or not isinstance(config, Mapping):
            return cls(reference_date=reference_date)

        raw = dict(config)
        match_section = raw.get("match")
        if isinstance(match_section, Mapping):
            raw = {**raw, **dict(match_section)}

        tolerances: dict[str, str] = {}
        relative: dict[str, str] = {}
        for key, value in raw.items():
            if isinstance(value, Mapping):
                if "tolerance" in value:
                    tolerances[str(key)] = str(value["tolerance"])
                if "relative_tolerance" in value:
                    relative[str(key)] = str(value["relative_tolerance"])
        declared_tolerances = raw.get("tolerances")
        if isinstance(declared_tolerances, Mapping):
            tolerances.update({str(k): str(v) for k, v in declared_tolerances.items()})
        declared_relative = raw.get("relative_tolerances")
        if isinstance(declared_relative, Mapping):
            relative.update({str(k): str(v) for k, v in declared_relative.items()})

        ref = reference_date
        if ref is None:
            candidate = raw.get("reference_date")
            if isinstance(candidate, date):
                ref = candidate
            elif isinstance(candidate, str):
                try:
                    ref = date.fromisoformat(candidate)
                except ValueError:
                    ref = None

        return cls(
            tolerances=tolerances,
            relative_tolerances=relative,
            context_similarity_min=str(raw.get("context_similarity_min", "0.34")),
            obligation_similarity_min=str(raw.get("obligation_similarity_min", "0.5")),
            contradiction_requires_context=_as_bool(
                raw.get("contradiction_requires_context"), True
            ),
            conditional_mismatch_uncheckable=_as_bool(
                raw.get("conditional_mismatch_uncheckable"), True
            ),
            reference_date=ref,
            max_evidence_chars=_as_int(raw.get("max_evidence_chars"), 200_000),
        )

    def tolerance_for(self, kind_value: str) -> Decimal:
        """Absolute tolerance for ``kind_value`` as a Decimal (default zero)."""
        return as_decimal(self.tolerances.get(kind_value, "0"))

    def relative_tolerance_for(self, kind_value: str) -> Decimal:
        """Relative tolerance for ``kind_value`` as a Decimal (default zero)."""
        return as_decimal(self.relative_tolerances.get(kind_value, "0"))
