"""Stand-in for ``groundlens.types`` (contract section 2).

Installed by ``conftest.py`` **only when the real module is absent**, so this
branch of the tree can be tested before the types/determinism branch lands.
It is a verbatim transcription of the frozen contract; if the real module
disagrees with it, the real module wins and this file should be deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FactKind(str, Enum):
    NUMBER = "number"
    CURRENCY = "currency"
    PERCENT = "percent"
    DATE = "date"
    DURATION = "duration"
    DEADLINE = "deadline"
    CITATION = "citation"
    OBLIGATION = "obligation"


class Polarity(str, Enum):
    MUST = "must"
    MUST_NOT = "must_not"
    MAY = "may"
    NEED_NOT = "need_not"
    SHOULD = "should"


class Decision(str, Enum):
    CLEAR = "clear"
    ESCALATE = "escalate"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    FAIL = "fail"


class MatchState(str, Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    CONTRADICTED = "contradicted"
    UNCHECKABLE = "uncheckable"


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    text: str


@dataclass(frozen=True, slots=True)
class Fact:
    kind: FactKind
    raw: str
    span: tuple[int, int]
    normalised: str
    attrs: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Match:
    fact: Fact
    state: MatchState
    evidence_id: str | None = None
    evidence_span: tuple[int, int] | None = None
    evidence_value: str | None = None


@dataclass(frozen=True, slots=True)
class Finding:
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
    decision: Decision
    findings: tuple[Finding, ...] = field(default_factory=tuple)
