"""The two-stage pipeline: deterministic first stage gates the model-based second.

This is the coherent way the two stages fit together. Stage one is SGI/DGI,
deterministic and free. Only when the geometry cannot settle a case (its
``Check.escalate`` is set) does stage two spend model calls. You do not pay for a
model on the cases the geometry already cleared.

The module is named ``pipeline`` (not ``two_stage``) so it does not collide with
the exported :func:`two_stage` function.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundlens.check import Check, check
from groundlens.evaluate import evaluate
from groundlens.verify.detector import SampleConsistency, SelfCheckNLI, Verification


@dataclass(frozen=True, slots=True)
class TwoStageResult:
    """Outcome of a two-stage run.

    Attributes:
        stage1: The deterministic SGI/DGI reading.
        stage2: The model-based reading, or ``None`` if stage one settled it.
        final: The reading to act on (stage two if it ran, else stage one).
        escalated: Whether stage two ran.
    """

    stage1: Check
    stage2: Verification | None
    final: Check
    escalated: bool


def two_stage(
    question: str,
    answer: str,
    context: str | None = None,
    *,
    detector: SampleConsistency | None = None,
    model: str | None = None,
    always: bool = False,
    **detector_kwargs: object,
) -> TwoStageResult:
    """Run the deterministic first stage, escalating to the model-based second only if needed.

    Args:
        question: The input query.
        answer: The answer to check.
        context: Optional source document. Present -> SGI, absent -> DGI (stage one).
        detector: A prebuilt second-stage detector to reuse (avoids reloading the
            model per call). If ``None`` and escalation happens, a
            :class:`~groundlens.verify.SelfCheckNLI` is built from ``model``.
        model: HF model id for the default detector, used only if ``detector`` is None.
        always: Run stage two even when stage one did not ask to escalate.
        **detector_kwargs: Forwarded to the default detector when one is built.

    Returns:
        A :class:`TwoStageResult`; ``.final`` is the :class:`~groundlens.check.Check`
        to act on.
    """
    stage1 = check(evaluate(question=question, response=answer, context=context))
    if not (stage1.escalate or always):
        return TwoStageResult(stage1=stage1, stage2=None, final=stage1, escalated=False)

    det = detector if detector is not None else SelfCheckNLI(model=model, **detector_kwargs)  # type: ignore[arg-type]
    stage2 = det.verify(question, answer)
    return TwoStageResult(stage1=stage1, stage2=stage2, final=stage2.check, escalated=True)
