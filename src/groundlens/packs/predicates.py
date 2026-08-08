"""Named predicate registry — the pack format's escape hatch, kept honest.

A pack references a predicate by dotted name only. The Python lives here, in
the library, under review and under test. A pack cannot smuggle code in.

Every registration records the SHA-256 of the callable's source text, taken
with :func:`inspect.getsource`. That hash goes into the audit record next to
the pack's content hash, so "which code ran" is answerable from the record
alone, without trusting a version label.

Ratio discipline: every rule that needs a predicate is a rule the declarative
format failed to express. The count of predicate rules against total rules is
the honest measure of whether the format is adequate, so resist adding one.
"""

from __future__ import annotations

import hashlib
import inspect
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import datetime
    from collections.abc import Callable, Mapping

    from groundlens.types import Evidence, Fact, Match

__all__ = [
    "REGISTRY",
    "PredicateContext",
    "PredicateEntry",
    "PredicateError",
    "PredicateRegistry",
    "entry",
    "get",
    "names",
    "register",
]


class PredicateError(LookupError):
    """A predicate name is unknown, already taken, or not source-inspectable."""


@dataclass(frozen=True, slots=True)
class PredicateContext:
    """Everything a predicate is allowed to look at.

    Deliberately a closed set. A predicate that needs something absent from
    this context is asking for a capability the control path does not have,
    and the answer is to widen the context under review, not to reach out.

    Attributes:
        answer: The NFKC-normalised answer text. All spans index into this.
        evidence: The evidence passed to ``check()``, sorted by id.
        facts: Facts extracted from :attr:`answer`.
        matches: Match outcomes, one per fact, in the same order.
        metadata: The caller's metadata mapping. Values never enter the audit
            record; only key names do.
        tools_output: Optional tool transcript, NFKC-normalised.
        reference_date: The caller-supplied date relative dates resolve
            against. There is no wall clock in this path.
        locale_profile: From the pack. Never from the environment.
    """

    answer: str
    evidence: tuple[Evidence, ...]
    facts: tuple[Fact, ...]
    matches: tuple[Match, ...]
    metadata: Mapping[str, Any]
    tools_output: str | None
    reference_date: datetime.date | None
    locale_profile: str


@dataclass(frozen=True, slots=True)
class PredicateEntry:
    """A registered predicate and the hash of the source that implements it."""

    name: str
    func: Callable[[PredicateContext], bool]
    source_sha256: str
    description: str


class PredicateRegistry:
    """A name-to-callable mapping that records each callable's source hash."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[str, PredicateEntry] = {}

    def register(
        self,
        name: str,
        func: Callable[[PredicateContext], bool],
        *,
        description: str = "",
    ) -> Callable[[PredicateContext], bool]:
        """Register ``func`` under ``name`` and hash its source.

        Args:
            name: Dotted, lowercase name, e.g. ``banking.disclosure_present``.
            func: A module-level function taking a :class:`PredicateContext`.
            description: One line of plain language for the reviewer.

        Returns:
            ``func``, so this can be used as a decorator factory.

        Raises:
            PredicateError: If the name is already taken, is not a valid
                dotted name, or the callable's source cannot be read.
        """
        if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", name):
            msg = (
                f"predicate name {name!r} must be dotted lowercase with at "
                "least two segments, e.g. 'banking.disclosure_present'"
            )
            raise PredicateError(msg)
        if name in self._entries:
            msg = (
                f"predicate {name!r} is already registered. Names are an audit "
                "identity: silently replacing one would make the recorded "
                "source hash disagree with the code that ran."
            )
            raise PredicateError(msg)
        try:
            source = inspect.getsource(func)
        except (OSError, TypeError) as exc:
            msg = (
                f"cannot read the source of predicate {name!r}. Predicates must "
                "be module-level functions in a real file so their source hash "
                "can be recorded in the audit record."
            )
            raise PredicateError(msg) from exc
        self._entries[name] = PredicateEntry(
            name=name,
            func=func,
            source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            description=description,
        )
        return func

    def entry(self, name: str) -> PredicateEntry:
        """Return the registry entry for ``name``.

        Raises:
            PredicateError: If ``name`` is not registered.
        """
        try:
            return self._entries[name]
        except KeyError as exc:
            known = ", ".join(sorted(self._entries)) or "(none)"
            msg = f"unknown predicate {name!r}. Registered predicates: {known}"
            raise PredicateError(msg) from exc

    def get(self, name: str) -> Callable[[PredicateContext], bool]:
        """Return the callable registered under ``name``."""
        return self.entry(name).func

    def names(self) -> tuple[str, ...]:
        """Return all registered names, sorted."""
        return tuple(sorted(self._entries))

    def __contains__(self, name: object) -> bool:
        """Return whether ``name`` is registered."""
        return name in self._entries


REGISTRY = PredicateRegistry()
"""The default registry. Packs resolve against this unless told otherwise."""


def register(
    name: str,
    func: Callable[[PredicateContext], bool],
    *,
    description: str = "",
) -> Callable[[PredicateContext], bool]:
    """Register a predicate in the default :data:`REGISTRY`."""
    return REGISTRY.register(name, func, description=description)


def get(name: str) -> Callable[[PredicateContext], bool]:
    """Look up a predicate in the default :data:`REGISTRY`."""
    return REGISTRY.get(name)


def entry(name: str) -> PredicateEntry:
    """Look up a registry entry in the default :data:`REGISTRY`."""
    return REGISTRY.entry(name)


def names() -> tuple[str, ...]:
    """Return the default registry's names, sorted."""
    return REGISTRY.names()


# ── Shared helpers ──────────────────────────────────────────────────────────

_WORD_RE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
_NUMERIC_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_SENTENCE_END_RE = re.compile(r"[.!?]")
_GATE_ID_RE = re.compile(r"\bK\d_\d+\b|\bgate\b|\bthreshold\b", re.IGNORECASE)
_CONFIDENCE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?%|\b(?:confidence|probability|likelihood)\s+(?:of\s+)?\d+",
    re.IGNORECASE,
)
_CAUSAL_CONNECTIVES: tuple[str, ...] = ("because", "due to", "therefore", "consequently")

_GOVERNANCE_DIMENSIONS: tuple[str, ...] = (
    "borrower",
    "collateral",
    "compliance",
    "control",
    "counterparty",
    "customer",
    "exposure",
    "jurisdiction",
    "limit",
    "policy",
    "regulator",
    "risk",
    "security",
    "transaction",
)

_INDEPENDENT_VALIDATION_PHRASES: tuple[str, ...] = (
    "checked by",
    "effective challenge",
    "independent review",
    "independent validation",
    "reviewed by",
    "second opinion",
    "validated by",
    "verified by",
)

_CASE_DETAIL_PHRASES: tuple[str, ...] = (
    "amount",
    "counterparty",
    "jurisdiction",
    "tenure",
    "transaction",
)

_DISCLOSURE_PHRASES: tuple[str, ...] = (
    "esta informacion no constituye asesoramiento",
    "this information does not constitute advice",
    "this is not a binding offer",
    "no constituye una oferta vinculante",
)


def _folded(text: str) -> str:
    return text.casefold()


def _token_count(text: str) -> int:
    return len(text.split())


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    folded = _folded(text)
    return any(phrase.casefold() in folded for phrase in phrases)


def _metadata_flag(metadata: Mapping[str, Any], key: str) -> bool:
    """Read a metadata flag with no default.

    Absent means false, never true. The old engine defaulted several of these
    to "pass when the metadata is missing", which is precisely the silent pass
    that fail-closed exists to remove.
    """
    value = metadata.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.casefold() in {"true", "yes", "1"}
    return False


# ── Shipped predicates ──────────────────────────────────────────────────────


def content_overlap_with_evidence(ctx: PredicateContext) -> bool:
    """At least 40 percent of the answer's content-word types occur in evidence.

    Integer arithmetic only: ``10 * overlap >= 4 * total``.
    """
    answer_words = set(_WORD_RE.findall(_folded(ctx.answer)))
    if not answer_words:
        return True
    evidence_words: set[str] = set()
    for item in ctx.evidence:
        evidence_words |= set(_WORD_RE.findall(_folded(item.text)))
    overlap = len(answer_words & evidence_words)
    return 10 * overlap >= 4 * len(answer_words)


def two_or_more_sentences(ctx: PredicateContext) -> bool:
    """The answer decomposes into at least two sentence-level claims."""
    return len(_SENTENCE_END_RE.findall(ctx.answer)) >= 2


def numeric_value_present(ctx: PredicateContext) -> bool:
    """The answer states at least one numeric value."""
    return _NUMERIC_RE.search(ctx.answer) is not None


def percent_or_confidence_present(ctx: PredicateContext) -> bool:
    """The answer carries a numeric confidence, probability or percentage."""
    return _CONFIDENCE_RE.search(ctx.answer) is not None


def numeric_with_causal_connective(ctx: PredicateContext) -> bool:
    """The answer couples a numeric claim to an explicit causal connective."""
    if _NUMERIC_RE.search(ctx.answer) is None:
        return False
    return _contains_any(ctx.answer, _CAUSAL_CONNECTIVES)


def at_least_20_tokens(ctx: PredicateContext) -> bool:
    """The answer is longer than 20 whitespace-separated tokens."""
    return _token_count(ctx.answer) > 20


def at_least_25_tokens(ctx: PredicateContext) -> bool:
    """The answer is longer than 25 whitespace-separated tokens."""
    return _token_count(ctx.answer) > 25


def at_least_30_tokens(ctx: PredicateContext) -> bool:
    """The answer is longer than 30 whitespace-separated tokens."""
    return _token_count(ctx.answer) > 30


def governance_dimensions_two_or_more(ctx: PredicateContext) -> bool:
    """The answer names at least two distinct governance dimensions."""
    folded = _folded(ctx.answer)
    hits = sum(1 for dimension in _GOVERNANCE_DIMENSIONS if dimension in folded)
    return hits >= 2


def gate_identifier_present(ctx: PredicateContext) -> bool:
    """The answer names a gate or threshold, by identifier or by word."""
    return _GATE_ID_RE.search(ctx.answer) is not None


def case_specific_detail(ctx: PredicateContext) -> bool:
    """The answer cites a case-specific detail, including ones from metadata.

    Static phrases plus the values of ``jurisdiction`` and ``transaction_type``
    when the caller supplied them. Metadata values are read here but never
    written to the audit record.
    """
    if _contains_any(ctx.answer, _CASE_DETAIL_PHRASES):
        return True
    folded = _folded(ctx.answer)
    for key in ("jurisdiction", "transaction_type"):
        value = ctx.metadata.get(key)
        if isinstance(value, str) and value.strip():
            needle = value.replace("_", " ").casefold()
            if needle in folded:
                return True
    return False


def independent_validation(ctx: PredicateContext) -> bool:
    """The answer or the metadata reports independent validation.

    A disjunction across two different sources, which is why it cannot be
    written as one declarative assert.
    """
    if _contains_any(ctx.answer, _INDEPENDENT_VALIDATION_PHRASES):
        return True
    return _metadata_flag(ctx.metadata, "independent_review_completed")


def disclosure_present(ctx: PredicateContext) -> bool:
    """The required non-advice disclosure block appears in the answer.

    The accepted wordings are fixed. A near-miss paraphrase fails, because a
    disclosure that a regulator has not seen the wording of is not a
    disclosure.
    """
    return _contains_any(ctx.answer, _DISCLOSURE_PHRASES)


register(
    "text.content_overlap_with_evidence",
    content_overlap_with_evidence,
    description="At least 40% of answer content-word types appear in the evidence.",
)
register(
    "text.two_or_more_sentences",
    two_or_more_sentences,
    description="Answer decomposes into at least two sentence-level claims.",
)
register(
    "text.numeric_value_present",
    numeric_value_present,
    description="Answer states at least one numeric value.",
)
register(
    "text.percent_or_confidence_present",
    percent_or_confidence_present,
    description="Answer carries a numeric confidence, probability or percentage.",
)
register(
    "text.numeric_with_causal_connective",
    numeric_with_causal_connective,
    description="Answer couples a numeric claim to a causal connective.",
)
register(
    "text.at_least_20_tokens",
    at_least_20_tokens,
    description="Answer is longer than 20 tokens.",
)
register(
    "text.at_least_25_tokens",
    at_least_25_tokens,
    description="Answer is longer than 25 tokens.",
)
register(
    "text.at_least_30_tokens",
    at_least_30_tokens,
    description="Answer is longer than 30 tokens.",
)
register(
    "banking.governance_dimensions_two_or_more",
    governance_dimensions_two_or_more,
    description="Answer names at least two distinct governance dimensions.",
)
register(
    "banking.gate_identifier_present",
    gate_identifier_present,
    description="Answer names a gate or threshold by identifier or word.",
)
register(
    "banking.case_specific_detail",
    case_specific_detail,
    description="Answer cites a case-specific detail, including metadata-supplied ones.",
)
register(
    "banking.independent_validation",
    independent_validation,
    description="Answer text or metadata reports independent validation.",
)
register(
    "banking.disclosure_present",
    disclosure_present,
    description="The required non-advice disclosure block appears verbatim.",
)
