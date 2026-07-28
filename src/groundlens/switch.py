"""GroundingSwitch — stage-2 context-protection control.

Sits between Geometry (SGI/DGI) and Consistency in the verification pipeline.
Converts a geometric score into a deterministic decision about whether the
response may be written into agent or RAG state.

Why this exists
---------------
In long-running agents and RAG pipelines the *context* (history, retrieved
documents, previous model outputs) can dominate parametric memory. When that
context is contaminated — a previous hallucination, a bad retrieval, a
degraded compaction — the model tends to propagate the error. The geometric
score already detects the misalignment; the Switch turns that signal into an
action that prevents the bad answer from entering the next turn's context.

Pipeline position
-----------------

    01 Geometry      SGI / DGI          (deterministic, no model)
    02 Switch        THIS MODULE       (deterministic, no model)
    03 Consistency   resample          (small open model)
    04 Rules         policy checks     (deterministic)
    05 LLM-as-judge
    06 Human review

Actions
-------
- ``ACCEPT``     — score is clearly grounded; safe to write into state.
- ``REJECT``     — score is clearly ungrounded; drop the response.
- ``FALLBACK``   — ungrounded; discard context influence / fall back to
                   parametric knowledge (caller decides how).
- ``REGENERATE`` — ungrounded; ask the model again, optionally with reduced
                   context weight.
- ``ESCALATE``   — geometry is ambiguous; continue to Consistency / later stages.

The default ``on_reject`` is ``FALLBACK`` because the most common failure mode
the Switch addresses is *contaminated context dominating the answer*. Rejecting
without a recovery path is often too harsh; regenerating is more expensive.
Callers can override per instance.

This module has **no model dependency** and never leaves the deterministic
core. Importing it does not load embeddings or LLMs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from groundlens._internal.thresholds import (
    DGI_PASS,
    SGI_REVIEW,
    SGI_STRONG_PASS,
)
from groundlens.check import Check, check
from groundlens.score import DGIResult, GroundlensScore, SGIResult

# ── Actions ─────────────────────────────────────────────────────────────────


class SwitchAction(str, Enum):
    """Decision produced by :class:`GroundingSwitch`.

    Values are lowercase strings so they serialise cleanly in audit logs and
    JSON without extra conversion.
    """

    ACCEPT = "accept"
    REJECT = "reject"
    FALLBACK = "fallback"
    REGENERATE = "regenerate"
    ESCALATE = "escalate"


# Valid values for the ``on_reject`` constructor argument.
_ON_REJECT_ACTIONS: frozenset[SwitchAction] = frozenset(
    {
        SwitchAction.REJECT,
        SwitchAction.FALLBACK,
        SwitchAction.REGENERATE,
        SwitchAction.ESCALATE,
    }
)


# ── Decision result ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SwitchDecision:
    """Outcome of a :class:`GroundingSwitch` evaluation.

    Attributes:
        action: The control action to take.
        write_to_state: Whether the response is safe to write into agent/RAG
            state (history, memory, next-turn context). ``True`` only for
            ``ACCEPT``.
        reason: Short plain-language explanation of why this action was chosen.
        check: The canonical :class:`~groundlens.check.Check` for the underlying
            geometric score (same object the rest of the library already uses).
        score: Raw geometric score value.
        method: ``"sgi"`` or ``"dgi"``.
        level: Programmatic severity from the Check (``"ok"`` / ``"review"`` /
            ``"risk"``).
    """

    action: SwitchAction
    write_to_state: bool
    reason: str
    check: Check
    score: float
    method: str
    level: str

    def __str__(self) -> str:
        """One-line summary suitable for logs."""
        return (
            f"SwitchDecision(action={self.action.value}, "
            f"write_to_state={self.write_to_state}, "
            f"{self.method}={self.score:.3f}, level={self.level})"
        )


# ── Switch ──────────────────────────────────────────────────────────────────


class GroundingSwitch:
    """Deterministic context-protection control driven by geometric scores.

    Args:
        accept_threshold_sgi: SGI at or above this is ``ACCEPT``.
            Default: :data:`~groundlens._internal.thresholds.SGI_STRONG_PASS`
            (1.20).
        reject_threshold_sgi: SGI below this triggers the reject-path action.
            Default: :data:`~groundlens._internal.thresholds.SGI_REVIEW` (0.95).
            Scores in ``[reject_threshold_sgi, accept_threshold_sgi)`` escalate.
        accept_threshold_dgi: DGI at or above this is ``ACCEPT``.
            Default: :data:`~groundlens._internal.thresholds.DGI_PASS` (0.525).
            DGI is binary: there is no middle band; below the cut uses
            ``on_reject``.
        on_reject: Action taken when the score is clearly ungrounded.
            One of ``"reject"``, ``"fallback"``, ``"regenerate"``, ``"escalate"``.
            Default: ``"fallback"``.

    Raises:
        ValueError: If thresholds are inconsistent or ``on_reject`` is invalid.

    Example::

        from groundlens import compute_sgi, GroundingSwitch

        switch = GroundingSwitch()
        sgi = compute_sgi(question=q, context=ctx, response=answer)
        decision = switch.decide(sgi)

        if decision.write_to_state:
            state.append(answer)
        elif decision.action.value == "fallback":
            # discard retrieved context influence; re-ask or use parametric path
            ...
        elif decision.action.value == "escalate":
            # continue to Consistency / LLM-as-judge
            ...
    """

    def __init__(
        self,
        *,
        accept_threshold_sgi: float = SGI_STRONG_PASS,
        reject_threshold_sgi: float = SGI_REVIEW,
        accept_threshold_dgi: float = DGI_PASS,
        on_reject: str | SwitchAction = SwitchAction.FALLBACK,
    ) -> None:
        if reject_threshold_sgi > accept_threshold_sgi:
            msg = (
                f"reject_threshold_sgi ({reject_threshold_sgi}) must be "
                f"<= accept_threshold_sgi ({accept_threshold_sgi})."
            )
            raise ValueError(msg)

        action = (
            on_reject
            if isinstance(on_reject, SwitchAction)
            else SwitchAction(str(on_reject).lower())
        )
        if action not in _ON_REJECT_ACTIONS:
            allowed = ", ".join(sorted(a.value for a in _ON_REJECT_ACTIONS))
            msg = f"on_reject must be one of {{{allowed}}}, got {on_reject!r}."
            raise ValueError(msg)

        self.accept_threshold_sgi = float(accept_threshold_sgi)
        self.reject_threshold_sgi = float(reject_threshold_sgi)
        self.accept_threshold_dgi = float(accept_threshold_dgi)
        self.on_reject = action

    # ── public API ──────────────────────────────────────────────────────────

    def decide(
        self,
        result: SGIResult | DGIResult | GroundlensScore | Check,
    ) -> SwitchDecision:
        """Map a geometric score (or its Check) to a context-control decision.

        Args:
            result: An :class:`~groundlens.score.SGIResult`,
                :class:`~groundlens.score.DGIResult`,
                :class:`~groundlens.score.GroundlensScore`, or an already-built
                :class:`~groundlens.check.Check`.

        Returns:
            A :class:`SwitchDecision`.

        Raises:
            TypeError: If ``result`` is not a recognised groundlens type.
        """
        chk, method, score = self._coerce(result)

        if method == "sgi":
            action, reason = self._decide_sgi(score)
        elif method == "dgi":
            action, reason = self._decide_dgi(score)
        else:
            # Second-stage consistency checks (SC) are not geometry; treat
            # them as already-escalated material and pass through.
            action = SwitchAction.ESCALATE
            reason = (
                f"Non-geometric method {method!r}; Switch only acts on SGI/DGI. "
                "Escalating by default."
            )

        return SwitchDecision(
            action=action,
            write_to_state=(action is SwitchAction.ACCEPT),
            reason=reason,
            check=chk,
            score=score,
            method=method,
            level=chk.level,
        )

    def __call__(
        self,
        result: SGIResult | DGIResult | GroundlensScore | Check,
    ) -> SwitchDecision:
        """Alias for :meth:`decide` so the switch is usable as a callable."""
        return self.decide(result)

    # ── internals ───────────────────────────────────────────────────────────

    def _coerce(
        self,
        result: SGIResult | DGIResult | GroundlensScore | Check,
    ) -> tuple[Check, str, float]:
        """Normalise any accepted input to (Check, method, score)."""
        if isinstance(result, Check):
            return result, result.method, result.score

        if isinstance(result, GroundlensScore):
            detail = result.detail
            chk = check(detail)
            return chk, result.method, result.value

        if isinstance(result, (SGIResult, DGIResult)):
            chk = check(result)
            return chk, result.method, result.value

        msg = (
            "GroundingSwitch.decide() expects SGIResult, DGIResult, "
            f"GroundlensScore, or Check; got {type(result).__name__}."
        )
        raise TypeError(msg)

    def _decide_sgi(self, score: float) -> tuple[SwitchAction, str]:
        """Three-zone decision for SGI."""
        if score >= self.accept_threshold_sgi:
            return (
                SwitchAction.ACCEPT,
                f"SGI={score:.3f} >= {self.accept_threshold_sgi:.2f} "
                "(strong grounding); safe to write into state.",
            )
        if score < self.reject_threshold_sgi:
            return (
                self.on_reject,
                f"SGI={score:.3f} < {self.reject_threshold_sgi:.2f} "
                f"(weak/absent grounding); action={self.on_reject.value}.",
            )
        return (
            SwitchAction.ESCALATE,
            f"SGI={score:.3f} in uncertain band "
            f"[{self.reject_threshold_sgi:.2f}, {self.accept_threshold_sgi:.2f}); "
            "geometry cannot settle — escalate.",
        )

    def _decide_dgi(self, score: float) -> tuple[SwitchAction, str]:
        """Binary decision for DGI (no middle band in the calibrated cut)."""
        if score >= self.accept_threshold_dgi:
            return (
                SwitchAction.ACCEPT,
                f"DGI={score:.3f} >= {self.accept_threshold_dgi:.3f} "
                "(aligned with grounded direction); safe to write into state.",
            )
        return (
            self.on_reject,
            f"DGI={score:.3f} < {self.accept_threshold_dgi:.3f} "
            f"(not aligned with grounded direction); action={self.on_reject.value}.",
        )
