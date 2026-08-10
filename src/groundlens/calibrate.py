"""Turning scores into a threshold -- on your data, with the cost shown.

This library ships no threshold. This function is how you get one, and it is
deliberately awkward to use without seeing what it costs.

The reason is a measurement. Across five public RAG grounding benchmarks and
nine detectors -- two published encoder models, an NLI cross-encoder, an LLM
judge, and this metric -- **not one reaches a false-positive rate below 0.65 at
95% hallucination recall.** Several sit at 1.00, which is worse than random, on
benchmarks where they rank well by AUROC. A ranking metric can look respectable
while the operating point a production system runs at is unusable.

So :func:`calibrate` always returns the measured false-positive rate alongside
the threshold. You cannot extract the cut without being handed the bill.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from groundlens._types import AnchorProfile, OperatingPoint

#: Below this many labelled examples a 95%-recall threshold is estimated from a
#: handful of points and means nothing. Refusing is more useful than obliging.
MIN_LABELLED = 200

BOOTSTRAP_ROUNDS = 1000


def _threshold_at_recall(positives: list[float], target_recall: float) -> float:
    """Highest score that still catches ``target_recall`` of the defects.

    Scores run 0 (nothing supports this) to 1 (fully anchored), so a defect is
    flagged when its score is **at or below** the threshold.
    """
    ordered = sorted(positives)
    index = min(len(ordered) - 1, max(0, round(target_recall * len(ordered)) - 1))
    return ordered[index]


def _fpr(negatives: list[float], threshold: float) -> float:
    if not negatives:
        return float("nan")
    return sum(1 for s in negatives if s <= threshold) / len(negatives)


def calibrate(
    labelled: Sequence[tuple[AnchorProfile | float, bool]],
    *,
    target_recall: float = 0.95,
    seed: int = 0,
    min_labelled: int = MIN_LABELLED,
) -> OperatingPoint:
    """Find the threshold that catches ``target_recall`` of defects, and its cost.

    Args:
        labelled: ``(profile_or_score, is_defect)`` pairs from **your** traffic.
            A threshold fitted on someone else's distribution does not transfer;
            the grounded floor moves with answer length, style and domain.
        target_recall: the fraction of defects you require the cut to catch.
        seed: bootstrap seed. Fixed by default so the interval is reproducible.
        min_labelled: lower it only if you are exploring, never to deploy.

    Returns:
        An :class:`~groundlens.OperatingPoint` carrying ``threshold`` **and**
        ``fpr`` with a bootstrap 95% interval. Read the ``fpr`` first.

    Raises:
        ValueError: too few examples, no defects, or no clean examples.
    """
    if not 0.0 < target_recall <= 1.0:
        msg = f"target_recall must be in (0, 1]; got {target_recall}"
        raise ValueError(msg)

    scores = [p.score if isinstance(p, AnchorProfile) else float(p) for p, _ in labelled]
    labels = [bool(flag) for _, flag in labelled]

    if len(scores) < min_labelled:
        msg = (
            f"calibrate needs at least {min_labelled} labelled examples; got {len(scores)}. "
            "Below that, a 95%-recall threshold is estimated from a handful of points "
            "and the interval it produces is not worth reporting."
        )
        raise ValueError(msg)

    positives = [s for s, flag in zip(scores, labels, strict=True) if flag]
    negatives = [s for s, flag in zip(scores, labels, strict=True) if not flag]
    if not positives or not negatives:
        msg = "calibrate needs both defect and clean examples"
        raise ValueError(msg)

    threshold = _threshold_at_recall(positives, target_recall)
    achieved = sum(1 for s in positives if s <= threshold) / len(positives)
    fpr = _fpr(negatives, threshold)

    rng = random.Random(seed)
    resampled: list[float] = []
    for _ in range(BOOTSTRAP_ROUNDS):
        pos = [positives[rng.randrange(len(positives))] for _ in positives]
        neg = [negatives[rng.randrange(len(negatives))] for _ in negatives]
        resampled.append(_fpr(neg, _threshold_at_recall(pos, target_recall)))
    resampled.sort()
    low = resampled[int(0.025 * len(resampled))]
    high = resampled[min(len(resampled) - 1, int(0.975 * len(resampled)))]

    return OperatingPoint(
        threshold=threshold,
        target_recall=target_recall,
        achieved_recall=achieved,
        fpr=fpr,
        fpr_ci95=(low, high),
        n=len(scores),
        n_positive=len(positives),
    )
