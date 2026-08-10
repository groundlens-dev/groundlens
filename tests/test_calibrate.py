"""Calibration always hands back the bill."""

from __future__ import annotations

import random

import pytest

from groundlens import calibrate
from groundlens.calibrate import MIN_LABELLED


def synthetic(n: int = 400, separation: float = 0.4, seed: int = 7) -> list[tuple[float, bool]]:
    """Defects floor low, clean answers floor high, with heavy overlap.

    Overlap is the realistic case, not a pessimistic one: on five public
    benchmarks no method separates these two populations well enough to pick a
    cut that a production system can afford.
    """
    rng = random.Random(seed)
    rows: list[tuple[float, bool]] = []
    for _ in range(n // 2):
        rows.append((min(1.0, max(0.0, rng.gauss(0.5 - separation / 2, 0.25))), True))
        rows.append((min(1.0, max(0.0, rng.gauss(0.5 + separation / 2, 0.25))), False))
    return rows


def test_it_reaches_the_recall_it_was_asked_for() -> None:
    point = calibrate(synthetic(), target_recall=0.95)
    assert point.achieved_recall >= 0.95


def test_it_always_reports_what_that_recall_costs() -> None:
    point = calibrate(synthetic(), target_recall=0.95)
    assert 0.0 <= point.fpr <= 1.0
    low, high = point.fpr_ci95
    assert low <= point.fpr <= high


def test_higher_recall_costs_more_false_alarms() -> None:
    cheap = calibrate(synthetic(), target_recall=0.50)
    dear = calibrate(synthetic(), target_recall=0.95)
    assert dear.fpr >= cheap.fpr
    assert dear.threshold >= cheap.threshold


def test_a_realistic_detector_is_unusable_at_95_percent_recall() -> None:
    """Not a property of this library -- a property of the problem.

    This is the finding the whole rebuild rests on: across five benchmarks and
    nine detectors, nothing reaches an affordable false-positive rate at high
    recall. The test is here so nobody quietly ships a default threshold later.
    """
    point = calibrate(synthetic(separation=0.4), target_recall=0.95)
    # 0.48 on this synthetic. The measured figures on real benchmarks are worse:
    # the best of 45 method-dataset cells is 0.65, LettuceDetect sits at 0.99 on
    # RAGTruth while ranking best by AUROC, and an LLM judge is at 1.00 on all five.
    assert point.fpr > 0.40
    assert point.fpr_ci95[0] > 0.20


def test_it_refuses_to_guess_from_too_little_data() -> None:
    with pytest.raises(ValueError, match="at least"):
        calibrate(synthetic(n=50), target_recall=0.95)


def test_it_refuses_a_one_class_sample() -> None:
    rows = [(0.5, True)] * MIN_LABELLED
    with pytest.raises(ValueError, match="both defect and clean"):
        calibrate(rows, target_recall=0.95)


def test_it_refuses_a_nonsense_target() -> None:
    with pytest.raises(ValueError, match="target_recall"):
        calibrate(synthetic(), target_recall=1.5)


def test_the_interval_is_reproducible() -> None:
    rows = synthetic()
    assert calibrate(rows).fpr_ci95 == calibrate(rows).fpr_ci95


def test_it_accepts_proofreads_as_well_as_bare_floats() -> None:
    from conftest import INVOICE_CONTEXT, INVOICE_GROUNDED, INVOICE_PERTURBED, FakeEncoder

    from groundlens import proofread

    encoder = FakeEncoder(max_tokens=512)
    good = proofread(INVOICE_GROUNDED, INVOICE_CONTEXT, encoder=encoder)
    bad = proofread(INVOICE_PERTURBED, INVOICE_CONTEXT, encoder=encoder)
    rows = [(good, False), (bad, True)] * (MIN_LABELLED // 2)
    point = calibrate(rows, target_recall=0.95)
    assert point.fpr == 0.0
    assert point.n == MIN_LABELLED
