"""Canonical human-readable checks for groundlens scores.

Single source of truth for how SGI / DGI results are presented to people.
Everything downstream renders from here — the README, the docs, the stdio MCP
server, and the remote (HTTP) MCP — so the wording is identical everywhere.

Design principles:

- **The check LEVEL is the only calibrated part.** It comes from the
  empirically derived thresholds (SGI 1.20 / 0.95; DGI 0.30 / 0.0 — see
  :mod:`groundlens._internal.thresholds`). Nothing else claims calibration.
- **The LABEL and MESSAGE are plain language.** No jargon in the user-facing
  text: "grounding" and "hallucination" do not appear in a label. The headline
  word is ``CHECK``; the metric's full name ("Semantic Grounding Index")
  carries meaning for non-experts, the bare acronym does not, so both are shown.
- **Raw components are surfaced as an optional technical ``detail`` line**
  (``q_dist`` / ``ctx_dist`` for SGI, displacement ``magnitude`` for DGI). They
  are shown, not used to invent uncalibrated 2-D cut-points. Finer message
  splitting (e.g. "restates the question" vs "not in the source") needs
  calibrated cut-points on those components and is deferred until we have them.

A check does not rule on whether an answer is *true* — only on whether it is
*drawn from the source* (SGI) or *shaped like a grounded answer* (DGI).

Vocabulary (locked):

    SGI:  Supported by the document / Partly supported / Not supported by the document
    DGI:  Looks grounded / Partly grounded / Not grounded

Change wording HERE and it changes everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundlens._internal.thresholds import DGI_PASS, SGI_REVIEW, SGI_STRONG_PASS
from groundlens.score import DGIResult, GroundlensScore, SGIResult

HEADLINE = "CHECK"

# Programmatic severity levels (not shown to end users).
LEVEL_OK = "ok"
LEVEL_REVIEW = "review"
LEVEL_RISK = "risk"

# Second-stage handoff lines. Groundlens is stage 1; these tell the reader what
# the deterministic filter cannot settle and must be escalated.
HANDOFF_ESCALATE = (
    "Escalate to your second stage, an LLM judge or a human. Geometry cannot settle this one."
)
HANDOFF_OK = (
    "Grounding, not facts: a plausible wrong fact in the right frame would pass "
    "this check. Verify facts in a second stage."
)


@dataclass(frozen=True, slots=True)
class Check:
    """A plain-language reading of an SGI or DGI result.

    Attributes:
        headline: Always ``"CHECK"``.
        label: Short plain reading shown to the user (no jargon).
        message: One-line plain explanation of what the reading means.
        level: Programmatic severity — ``"ok"`` / ``"review"`` / ``"risk"``.
        method: ``"sgi"`` or ``"dgi"``.
        metric_name: Full metric name, e.g. ``"Semantic Grounding Index"``.
        metric_abbr: Metric acronym, e.g. ``"SGI"``.
        score: The raw metric value (``result.value``).
        detail: Optional technical line with the raw components.
        note: Optional standing caveat (DGI: no source was provided).
        escalate: True when this case must go to the second stage.
        handoff: Plain line naming the second-stage handoff.
    """

    headline: str
    label: str
    message: str
    level: str
    method: str
    metric_name: str
    metric_abbr: str
    score: float
    detail: str = ""
    note: str = ""
    escalate: bool = False
    handoff: str = ""

    def line(self) -> str:
        """The single headline line: ``CHECK: <label> (<name> - <ABBR>=x.xx)``."""
        return (
            f"{self.headline}: {self.label} "
            f"({self.metric_name} - {self.metric_abbr}={self.score:.2f})"
        )

    def render(self) -> str:
        """Full multi-line rendering: headline, message, note, handoff."""
        parts = [self.line(), self.message]
        if self.note:
            parts.append(self.note)
        if self.handoff:
            parts.append(self.handoff)
        return "\n".join(parts)

    def __str__(self) -> str:
        """Return the full multi-line rendering (same as :meth:`render`)."""
        return self.render()


def check_for_sgi(result: SGIResult) -> Check:
    """Build the canonical :class:`Check` for an SGI result."""
    v = result.value
    if v >= SGI_STRONG_PASS:
        level = LEVEL_OK
        label = "Supported by the document"
        message = "The answer draws on the source and adds detail beyond the question."
        escalate, handoff = False, HANDOFF_OK
    elif v >= SGI_REVIEW:
        level = LEVEL_REVIEW
        label = "Partly supported"
        message = "The answer is only partly drawn from the source — worth a look."
        escalate, handoff = True, HANDOFF_ESCALATE
    else:
        level = LEVEL_RISK
        label = "Not supported by the document"
        message = (
            "The answer stays closer to the question than to the source, so it may "
            "not come from the document. Check it before trusting it."
        )
        escalate, handoff = True, HANDOFF_ESCALATE
    detail = f"distance to source {result.ctx_dist:.2f}, distance to question {result.q_dist:.2f}"
    return Check(
        headline=HEADLINE,
        label=label,
        message=message,
        level=level,
        method="sgi",
        metric_name="Semantic Grounding Index",
        metric_abbr="SGI",
        score=v,
        detail=detail,
        escalate=escalate,
        handoff=handoff,
    )


def check_for_dgi(result: DGIResult) -> Check:
    """Build the canonical :class:`Check` for a DGI result."""
    v = result.value
    if v >= DGI_PASS:
        level = LEVEL_OK
        label = "Looks grounded"
        message = "The answer moves the way well-grounded answers usually do."
        escalate, handoff = False, HANDOFF_OK
    elif v >= 0.0:
        level = LEVEL_REVIEW
        label = "Partly grounded"
        message = "The answer only weakly follows a grounded pattern — worth a look."
        escalate, handoff = True, HANDOFF_ESCALATE
    else:
        level = LEVEL_RISK
        label = "Not grounded"
        message = (
            "The answer moves opposite to the way grounded answers do. "
            "Check it before trusting it."
        )
        escalate, handoff = True, HANDOFF_ESCALATE
    return Check(
        headline=HEADLINE,
        label=label,
        message=message,
        level=level,
        method="dgi",
        metric_name="Directional Grounding Index",
        metric_abbr="DGI",
        score=v,
        detail=f"commitment (how far the answer moved from the question) {result.magnitude:.2f}",
        note="No source given — judged by the shape of the answer.",
        escalate=escalate,
        handoff=handoff,
    )


def check(result: SGIResult | DGIResult | GroundlensScore) -> Check:
    """Return the canonical :class:`Check` for any groundlens score.

    Accepts an :class:`~groundlens.score.SGIResult`, a
    :class:`~groundlens.score.DGIResult`, or a
    :class:`~groundlens.score.GroundlensScore` (from ``evaluate()``), and
    dispatches to the right renderer.

    Raises:
        TypeError: If ``result`` is not a recognized groundlens score type.
    """
    if isinstance(result, GroundlensScore):
        result = result.detail
    if isinstance(result, SGIResult):
        return check_for_sgi(result)
    if isinstance(result, DGIResult):
        return check_for_dgi(result)
    msg = (
        "check() expects an SGIResult, DGIResult, or GroundlensScore, "
        f"got {type(result).__name__}."
    )
    raise TypeError(msg)
