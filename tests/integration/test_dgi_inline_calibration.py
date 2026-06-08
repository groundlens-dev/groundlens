"""Integration tests for DGI inline calibration (DGI.calibrate(pairs=...)).

Regression tests for the bug in which ``DGI.score()`` always fell through
to the bundled mu_hat even after ``calibrate(pairs=...)`` populated the
inline cache. The bug was: ``DGI.score`` passed ``reference_csv=None`` to
``compute_dgi`` whenever the sentinel was ``"__inline__"``, which made
``_get_mu_hat`` look up the bundled cache key.

These tests load the real embedding model and verify two things:

1. After ``calibrate(pairs=...)``, ``score()`` produces a result that
   differs from the bundled-calibration result on the same input. If the
   two are byte-identical, the inline calibration is not being applied.
2. Calling ``score()`` with the inline sentinel but no prior ``calibrate``
   raises ``RuntimeError`` with a clear message.
"""

from __future__ import annotations

import pytest

from groundlens.dgi import DGI, compute_dgi, reset_calibration_cache

pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def _clear_dgi_cache() -> None:
    """Ensure a clean calibration cache for each test."""
    reset_calibration_cache()


class TestInlineCalibrationIsApplied:
    """Calibrating with explicit pairs must change the score vs bundled."""

    def test_inline_calibration_differs_from_bundled(self) -> None:
        # Bundled baseline
        bundled = compute_dgi(
            question="What is the capital of France?",
            response="The capital of France is Paris.",
        )

        # Inline calibration with a small domain-specific corpus
        dgi = DGI()
        dgi.calibrate(
            pairs=[
                ("What is the capital of Germany?", "The capital of Germany is Berlin."),
                ("What is the capital of Italy?", "The capital of Italy is Rome."),
                ("What is the capital of Spain?", "The capital of Spain is Madrid."),
                ("What is the capital of Portugal?", "The capital of Portugal is Lisbon."),
                ("What is the capital of Belgium?", "The capital of Belgium is Brussels."),
            ]
        )
        inline = dgi.score(
            question="What is the capital of France?",
            response="The capital of France is Paris.",
        )

        # Sanity: both produce finite values
        assert -1.0 <= bundled.value <= 1.0
        assert -1.0 <= inline.value <= 1.0

        # The fix: inline value must differ from bundled.
        # Pre-fix, the two were byte-identical.
        assert inline.value != bundled.value, (
            "Inline calibration did not change the DGI score — the bug "
            "where DGI.score() always falls back to the bundled mu_hat "
            "is still present."
        )

    def test_inline_calibration_uses_correct_cache_key(self) -> None:
        """After calibrate(pairs=...) the inline cache key is populated."""
        from groundlens.dgi import _mu_hat_cache

        dgi = DGI()
        dgi.calibrate(
            pairs=[
                ("Q1", "A1 with concrete factual detail."),
                ("Q2", "A2 with concrete factual detail."),
            ]
        )
        # Cache must contain the (model, "__inline__") key.
        assert (dgi.model, "__inline__") in _mu_hat_cache


class TestInlineWithoutCalibrate:
    """Using the inline sentinel without first calibrating must raise."""

    def test_score_without_calibrate_raises(self) -> None:
        dgi = DGI()
        # Manually set the inline sentinel without populating the cache.
        dgi.reference_csv = "__inline__"
        with pytest.raises(RuntimeError, match="calibrate"):
            dgi.score(
                question="What is the capital of France?",
                response="The capital of France is Paris.",
            )

    def test_compute_dgi_with_inline_sentinel_raises(self) -> None:
        """Direct compute_dgi(reference_csv='__inline__') without cache raises."""
        with pytest.raises(RuntimeError, match="inline calibration not initialized"):
            compute_dgi(
                question="What is the capital of France?",
                response="The capital of France is Paris.",
                reference_csv="__inline__",
            )
