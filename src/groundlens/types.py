"""Core value types for the groundlens v2 control path.

These are the types the frozen v2 interface contract fixes in place:
every extractor, matcher, rule engine and reporter in the codebase
speaks in them, so nothing here may be renamed or given a different
string value once shipped.

Three properties hold for every type in this module, and the suite in
``tests/determinism/`` enforces all three:

* **No floats.** Nothing in a :class:`Result` is a float, anywhere, at
  any depth. Numbers that came from text live as canonical strings; the
  only numeric values are integer character offsets and integer counts.
* **Frozen and slotted.** Every dataclass is ``frozen=True, slots=True``.
  A finding cannot be edited after the fact, which is the point of an
  audit trail.
* **Standard library only.** This module imports nothing outside the
  standard library, so ``groundlens.types`` stays importable in the
  smallest possible install.

Spans are pairs of character offsets ``(start, end)``, half-open, into
the *normalised* text produced by
:func:`groundlens.determinism.normalise_text`. They never index into the
caller's raw input. See that module's docstring for the exact policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from groundlens.audit_record import AuditRecord

__all__ = [
    "Decision",
    "Evidence",
    "Fact",
    "FactKind",
    "Finding",
    "Match",
    "MatchState",
    "Polarity",
    "Result",
    "Severity",
]


# ── Enumerations ────────────────────────────────────────────────────────────


class FactKind(str, Enum):
    """The kind of checkable fact an extractor produced.

    Values are stable strings; they appear inside finding codes
    (``fact.unmatched.currency``) and in serialised records.
    """

    NUMBER = "number"
    CURRENCY = "currency"
    PERCENT = "percent"
    DATE = "date"
    DURATION = "duration"
    DEADLINE = "deadline"
    CITATION = "citation"
    OBLIGATION = "obligation"


class Polarity(str, Enum):
    """The deontic strength of an obligation-shaped statement.

    Used by the ``obligation_polarity_consistent`` assertion: an answer
    may not state a stronger duty than the evidence supports.
    """

    MUST = "must"  # obligation
    MUST_NOT = "must_not"  # prohibition
    MAY = "may"  # permission
    NEED_NOT = "need_not"  # exemption
    SHOULD = "should"  # recommendation


class Decision(str, Enum):
    """The only two outcomes groundlens ever returns.

    There is no score and no confidence. Either the answer clears the
    pack, or a human looks at it.
    """

    CLEAR = "clear"
    ESCALATE = "escalate"


class Severity(str, Enum):
    """How much a single finding matters."""

    INFO = "info"
    WARN = "warn"
    FAIL = "fail"


class MatchState(str, Enum):
    """The outcome of trying to ground one fact in the evidence."""

    MATCHED = "matched"
    UNMATCHED = "unmatched"
    CONTRADICTED = "contradicted"  # found in evidence with a different value
    UNCHECKABLE = "uncheckable"  # extractor found it, matcher cannot decide


# ── Values ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Evidence:
    """One retrievable unit of source text the answer is checked against.

    Attributes:
        id: Caller-supplied, stable identifier, e.g. ``"doc-1#p3"``. It
            is what appears in findings and in the audit record, so it
            must survive a re-run of the retrieval step unchanged.
        text: The evidence text. Normalised on the way in, like the
            answer, so that evidence spans mean the same thing.
    """

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class Fact:
    """A checkable claim the extractor located in the answer.

    Attributes:
        kind: Which extractor produced it.
        raw: The exact substring of the NFKC-normalised answer, so a
            reviewer can see the claim as it was written.
        span: Half-open character offsets ``(start, end)`` into the
            NFKC-normalised answer. Never into the raw input.
        normalised: The canonical string form used for comparison, e.g.
            ``"1234.56"`` for a currency amount or ``"2026-08-08"`` for
            a date. Never a float: see
            :func:`groundlens.determinism.canonical_decimal_str`.
        attrs: Extra key/value pairs, sorted by key, string values only.
            Currency codes, date granularity and polarity live here.
    """

    kind: FactKind
    raw: str
    span: tuple[int, int]
    normalised: str
    attrs: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Match:
    """The result of trying to ground one :class:`Fact` in the evidence.

    Attributes:
        fact: The fact that was looked up.
        state: What the matcher concluded.
        evidence_id: Which evidence unit the fact was found in, when it
            was found at all.
        evidence_span: Half-open offsets into that evidence unit's
            normalised text.
        evidence_value: The differing value found in the evidence. Set
            when ``state`` is :attr:`MatchState.CONTRADICTED`, so a
            reviewer sees both numbers without opening the source.
    """

    fact: Fact
    state: MatchState
    evidence_id: str | None = None
    evidence_span: tuple[int, int] | None = None
    evidence_value: str | None = None


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing a reviewer needs to know about an answer.

    Attributes:
        code: Stable machine code, dotted, lowercase, ASCII, e.g.
            ``"fact.unmatched.currency"``. Codes are additive only and
            are never renamed once shipped.
        severity: How much it matters. Any ``FAIL`` escalates.
        message: Plain language, no jargon and no acronyms. It is read
            by compliance staff, not by engineers.
        fact: The fact the finding is about, when there is one.
        match: The match attempt behind the finding, when there is one.
        rule_id: The pack rule that fired, e.g. ``"BNK-001"``.
        evidence_id: The evidence unit involved, when there is one.
        evidence_span: Half-open offsets into that evidence unit.
    """

    code: str
    severity: Severity
    message: str
    fact: Fact | None = None
    match: Match | None = None
    rule_id: str | None = None
    evidence_id: str | None = None
    evidence_span: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class Result:
    """What :func:`groundlens.check` returns.

    Carries no score, no confidence and no float. Anyone who adds one
    breaks the determinism rules and the CI gate that enforces them.

    Attributes:
        decision: Clear, or escalate to a human.
        findings: Every finding, in the canonical order produced by
            :func:`groundlens.determinism.sort_findings`.
        audit: The record that makes the decision reproducible by a
            third party who has the same inputs and the same pack.
    """

    decision: Decision
    findings: tuple[Finding, ...]
    audit: AuditRecord
