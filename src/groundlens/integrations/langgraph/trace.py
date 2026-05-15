"""Structured trace types for LangGraph agent execution.

Collects groundlens scores and metadata from each step of a LangGraph
agent pipeline into a structured, serializable trace. Supports triage
summaries, JSON export, and self-contained HTML reports.

Example:
    >>> from groundlens.integrations.langgraph import GroundlensLangGraphCallback
    >>> trace = callback.get_trace()
    >>> print(trace.summary())
    >>> trace.to_html("report.html")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from groundlens.score import GroundlensScore


# ── Triage classification ────────────────────────────────────────────────────


def _triage_label(score: GroundlensScore) -> str:
    """Classify a groundlens score into a triage category.

    Args:
        score: The evaluated GroundlensScore from SGI or DGI.

    Returns:
        One of ``"trusted"``, ``"review"``, or ``"flagged"``.
    """
    if score.flagged:
        return "flagged"
    if score.normalized < 0.6:
        return "review"
    return "trusted"


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class AgentStep:
    """A single evaluated step in a LangGraph agent execution.

    Attributes:
        node_name: LangGraph node that produced this LLM call.
        step_index: Execution order (0-based).
        input_text: Prompt sent to the LLM.
        output_text: LLM response text.
        context: Tool output or retrieved text used as grounding context,
            or ``None`` if no context was available (DGI mode).
        score: The groundlens evaluation result.
        triage: Triage classification: ``"trusted"``, ``"review"``, or ``"flagged"``.
        method: Scoring method used: ``"sgi"`` or ``"dgi"``.
        duration_ms: LLM call latency in milliseconds.
    """

    node_name: str
    step_index: int
    input_text: str
    output_text: str
    context: str | None
    score: GroundlensScore
    triage: str
    method: str
    duration_ms: float

    def to_dict(self) -> dict[str, object]:
        """Serialize step to a JSON-compatible dict.

        Returns:
            Dict with all step fields. The ``score`` field is expanded
            to its primitive attributes (value, normalized, flagged,
            method, explanation).
        """
        return {
            "node_name": self.node_name,
            "step_index": self.step_index,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "context": self.context,
            "triage": self.triage,
            "method": self.method,
            "duration_ms": self.duration_ms,
            "score": {
                "value": self.score.value,
                "normalized": self.score.normalized,
                "flagged": self.score.flagged,
                "method": self.score.method,
                "explanation": self.score.explanation,
            },
        }


@dataclass
class AgentTrace:
    """Complete trace of a LangGraph agent execution with groundlens triage.

    Accumulates :class:`AgentStep` instances and provides aggregate
    statistics, summaries, and export methods.

    Attributes:
        steps: Ordered list of evaluated agent steps.
    """

    steps: list[AgentStep] = field(default_factory=list)

    # ── Computed properties ───────────────────────────────────────────────

    @property
    def total_steps(self) -> int:
        """Total number of evaluated steps."""
        return len(self.steps)

    @property
    def flagged_steps(self) -> int:
        """Number of steps triaged as flagged."""
        return sum(1 for s in self.steps if s.triage == "flagged")

    @property
    def review_steps(self) -> int:
        """Number of steps triaged as needing review."""
        return sum(1 for s in self.steps if s.triage == "review")

    @property
    def trusted_steps(self) -> int:
        """Number of steps triaged as trusted."""
        return sum(1 for s in self.steps if s.triage == "trusted")

    @property
    def total_duration_ms(self) -> float:
        """Total LLM call time across all steps in milliseconds."""
        return sum(s.duration_ms for s in self.steps)

    # ── Public methods ────────────────────────────────────────────────────

    def summary(self) -> str:
        """Return a human-readable triage summary.

        Returns:
            Multi-line string summarizing step counts by triage category
            and listing any flagged or review steps by node name.

        Example:
            >>> print(trace.summary())
            Agent completed: 3 steps (142ms)
            ✓ 2 trusted  ⚠ 0 review  ✗ 1 flagged
            Flagged: fact_check (DGI=0.180)
        """
        lines = [
            f"Agent completed: {self.total_steps} steps ({self.total_duration_ms:.0f}ms)",
            (
                f"✓ {self.trusted_steps} trusted  "
                f"⚠ {self.review_steps} review  "
                f"✗ {self.flagged_steps} flagged"
            ),
        ]

        flagged = [s for s in self.steps if s.triage == "flagged"]
        if flagged:
            names = ", ".join(
                f"{s.node_name} ({s.method.upper()}={s.score.value:.3f})" for s in flagged
            )
            lines.append(f"Flagged: {names}")

        review = [s for s in self.steps if s.triage == "review"]
        if review:
            names = ", ".join(
                f"{s.node_name} ({s.method.upper()}={s.score.value:.3f})" for s in review
            )
            lines.append(f"Review: {names}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Serialize the full trace to a JSON-compatible dict.

        Returns:
            Dict containing summary counts and a list of serialized steps.
        """
        return {
            "total_steps": self.total_steps,
            "flagged_steps": self.flagged_steps,
            "review_steps": self.review_steps,
            "trusted_steps": self.trusted_steps,
            "total_duration_ms": self.total_duration_ms,
            "steps": [s.to_dict() for s in self.steps],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the trace to a JSON string.

        Args:
            indent: JSON indentation level. Defaults to 2.

        Returns:
            Pretty-printed JSON string of the trace.
        """
        return json.dumps(self.to_dict(), indent=indent)

    def to_html(self, path: str | Path | None = None) -> str:
        """Generate a self-contained HTML triage report.

        Args:
            path: Optional file path. If provided, the HTML is written
                to this file. Pass ``None`` to get the HTML string only.

        Returns:
            The complete HTML string.
        """
        from groundlens.integrations.langgraph.report import render_html_report

        html = render_html_report(self)
        if path is not None:
            Path(path).write_text(html, encoding="utf-8")
        return html
