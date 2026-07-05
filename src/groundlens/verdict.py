"""Canonical human-readable verdicts for groundlens scores.

Single source of truth for how SGI / DGI results are presented to people.
Everything downstream renders from here — the README, the docs, the stdio MCP
server, and the remote (HTTP) MCP — so the wording is identical everywhere.

Design principles:

- **The verdict LEVEL is the only calibrated part.** It comes from the
  empirically derived thresholds (SGI 1.20 / 0.95; DGI 0.30 / 0.0 — see
  :mod:`groundlens._internal.thresholds`). Nothing else claims calibration.
- **The LABEL and MESSAGE are plain language.** No jargon in the user-facing
  text: "grounding" and "hallucination" do not appear in a label. The headline
  word is ``VERIFICATION``; the metric's full name ("Semantic Grounding Index")
  carries meaning for non-experts, the bare acronym does not, so both are shown.
- **Raw components are surfaced as an optional technical ``detail`` line**
  (``q_dist`` / ``ctx_dist`` for SGI, displacement ``magnitude`` for DGI). They
  are shown, not used to invent uncalibrated 2-D cut-points. Finer message
  splitting (e.g. "restates the question" vs "not in the source") needs
  calibrated cut-points on those components and is deferred until we have them.

Vocabulary (locked):

    SGI:  Supported by the document / Partly supported / Not supported by the document
    DGI:  Looks grounded / Partly grounded / Not grounded

Change wording HERE and it changes everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundlens._internal.thresholds import DGI_PASS, SGI_REVIEW, SGI_STRONG_PASS
from groundlens.score import DGIResult, GroundlensScore, SGIResult

HEADLINE = "VERIFICATION"

# Programmatic severity levels (not shown to end users).
LEVEL_OK = "ok"
LEVEL_REVIEW = "review"
LEVEL_RISK = "risk"


@dataclass(frozen=True, slots=True)
class Verdict:
    """A plain-language reading of an SGI or DGI result.

    Attributes:
        headline: Always ``"VERIFICATION"``.
        label: Short plain verdict shown to the user (no jargon).
        message: One-line plain explanation of what the verdict means.
        level: Programmatic severity — ``"ok"`` / ``"review"`` / ``"risk"``.
        method: ``"sgi"`` or ``"dgi"``.
        metric_name: Full metric name, e.g. ``"Semantic Grounding Index"``.
        metric_abbr: Metric acronym, e.g. ``"SGI"``.
        score: The raw metric value (``result.value``).
        detail: Optional technical line with the raw components.
        note: Optional standing caveat (DGI: no source was provided).
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

    def line(self) -> str:
        """The single headline line: ``VERIFICATION: <label> (<name> - <ABBR>=x.xx)``."""
        return (
            f"{self.headline}: {self.label} "
            f"({self.metric_name} - {self.metric_abbr}={self.score:.2f})"
        )

    def render(self) -> str:
        """Full multi-line rendering: headline, message, optional note."""
        parts = [self.line(), self.message]
        if self.note:
            parts.append(self.note)
        return "\n".join(parts)

    def __str__(self) -> str:
        """Return the full multi-line rendering (same as :meth:`render`)."""
        return self.render()


def verdict_for_sgi(result: SGIResult) -> Verdict:
    """Build the canonical :class:`Verdict` for an SGI result."""
    v = result.value
    if v >= SGI_STRONG_PASS:
        level = LEVEL_OK
        label = "Supported by the document"
        message = "The answer draws on the source and adds detail beyond the question."
    elif v >= SGI_REVIEW:
        level = LEVEL_REVIEW
        label = "Partly supported"
        message = "The answer is only partly drawn from the source — worth a check."
    else:
        level = LEVEL_RISK
        label = "Not supported by the document"
        message = (
            "The answer stays closer to the question than to the source, so it may "
            "not come from the document. Check it before trusting it."
        )
    detail = (
        f"distance to source {result.ctx_dist:.2f}, "
        f"distance to question {result.q_dist:.2f}"
    )
    return Verdict(
        headline=HEADLINE,
        label=label,
        message=message,
        level=level,
        method="sgi",
        metric_name="Semantic Grounding Index",
        metric_abbr="SGI",
        score=v,
        detail=detail,
    )


def verdict_for_dgi(result: DGIResult) -> Verdict:
    """Build the canonical :class:`Verdict` for a DGI result."""
    v = result.value
    if v >= DGI_PASS:
        level = LEVEL_OK
        label = "Looks grounded"
        message = "The answer moves the way well-grounded answers usually do."
    elif v >= 0.0:
        level = LEVEL_REVIEW
        label = "Partly grounded"
        message = "The answer only weakly follows a grounded pattern — worth a check."
    else:
        level = LEVEL_RISK
        label = "Not grounded"
        message = (
            "The answer moves opposite to the way grounded answers do. "
            "Check it before trusting it."
        )
    return Verdict(
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
    )


def verdict(result: SGIResult | DGIResult | GroundlensScore) -> Verdict:
    """Return the canonical :class:`Verdict` for any groundlens score.

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
        return verdict_for_sgi(result)
    if isinstance(result, DGIResult):
        return verdict_for_dgi(result)
    msg = (
        "verdict() expects an SGIResult, DGIResult, or GroundlensScore, "
        f"got {type(result).__name__}."
    )
    raise TypeError(msg)
