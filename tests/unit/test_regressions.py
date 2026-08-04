"""Regression tests: one per fixed defect, each named for what it locks down.

Every test here failed before the corresponding fix. They exist so the same
class of defect cannot come back silently.
"""

from __future__ import annotations

import numpy as np
import pytest

from groundlens._internal.embeddings import set_default_encoder
from groundlens._internal.thresholds import DGI_PASS, normalize_dgi, normalize_sgi
from groundlens.dgi import DGI, compute_dgi, reset_calibration_cache
from groundlens.evaluate import evaluate_batch
from groundlens.sgi import compute_sgi

_DIM = 768


def _det_encoder(seed: int = 0):
    """A deterministic, finite, well-conditioned stand-in encoder."""

    def _enc(texts: list[str]) -> np.ndarray:
        out = []
        for i, t in enumerate(texts):
            r = np.random.default_rng((abs(hash(t)) + seed + i) % (2**32))
            out.append(r.standard_normal(_DIM).astype(np.float32))
        return np.stack(out)

    return _enc


@pytest.fixture(autouse=True)
def _clean_encoder():
    """Never leak a process-global encoder between tests."""
    set_default_encoder(None)
    reset_calibration_cache()
    yield
    set_default_encoder(None)
    reset_calibration_cache()


class TestSGIFailsSafe:
    """A broken encoder must never read as a strong pass."""

    def test_nan_embeddings_do_not_read_as_a_strong_pass(self) -> None:
        set_default_encoder(lambda ts: np.full((len(ts), _DIM), np.nan, dtype=np.float32))
        result = compute_sgi(question="q text", context="c text", response="r text")
        assert result.flagged is True
        assert result.value == 0.0

    def test_inf_embeddings_do_not_read_as_a_strong_pass(self) -> None:
        set_default_encoder(lambda ts: np.full((len(ts), _DIM), np.inf, dtype=np.float32))
        assert compute_sgi(question="q", context="c", response="r").flagged is True

    def test_zero_norm_embeddings_are_flagged(self) -> None:
        set_default_encoder(lambda ts: np.zeros((len(ts), _DIM), dtype=np.float32))
        assert compute_sgi(question="q", context="c", response="r").flagged is True

    def test_healthy_embeddings_are_untouched_by_the_guard(self) -> None:
        set_default_encoder(_det_encoder())
        result = compute_sgi(question="q text", context="c text", response="r text")
        assert np.isfinite(result.value)
        assert result.value > 0.0

    def test_normalizers_do_not_launder_nan_into_a_score(self) -> None:
        assert normalize_sgi(float("nan")) == 0.0
        assert normalize_dgi(float("nan")) == 0.0


class TestDGIInlineCalibrationCacheKey:
    """calibrate() and score() must derive the cache key the way encode_texts does."""

    def test_calibrate_then_score_works_under_set_default_encoder(self) -> None:
        """The public torch-free path: set_default_encoder + DGI.calibrate(pairs=...)."""
        set_default_encoder(_det_encoder(7))
        pairs = [(f"Q{i}?", f"A{i} is the answer.") for i in range(10)]
        scorer = DGI()
        scorer.calibrate(pairs=pairs)
        # Used to raise RuntimeError("DGI inline calibration not initialized").
        assert -1.0 <= scorer.score(question="Q?", response="An answer.").value <= 1.0

    def test_calibrate_then_score_works_with_an_explicit_encoder(self) -> None:
        pairs = [(f"Q{i}?", f"A{i} is the answer.") for i in range(10)]
        scorer = DGI(encoder=_det_encoder(3))
        scorer.calibrate(pairs=pairs)
        assert -1.0 <= scorer.score(question="Q?", response="An answer.").value <= 1.0


class TestBatchValidatesUpFront:
    def test_bad_item_is_rejected_without_scoring_any_item(self) -> None:
        calls: list[int] = []

        def counting_encoder(texts: list[str]) -> np.ndarray:
            calls.append(len(texts))
            return _det_encoder()(texts)

        set_default_encoder(counting_encoder)
        items = [
            {"question": "Q1?", "response": "A1."},
            {"question": "Q2?", "response": ""},
        ]
        with pytest.raises(ValueError, match="Item 1"):
            evaluate_batch(items)
        assert calls == [], "a batch with an invalid item must not embed anything"


class TestThresholdIsSingleSourced:
    def test_dgi_pass_is_the_canonical_value(self) -> None:
        assert DGI_PASS == 0.525

    def test_flag_boundary_matches_dgi_pass_exactly(self) -> None:
        set_default_encoder(_det_encoder(11))
        result = compute_dgi(question="q text", response="r text")
        assert result.flagged == (result.value < DGI_PASS)

    def test_no_source_file_restates_a_stale_dgi_cut(self) -> None:
        from pathlib import Path

        import groundlens

        root = Path(groundlens.__file__).parent
        offenders = [
            f"{path.name}: 0.594"
            for path in root.rglob("*.py")
            if "0.594" in path.read_text(encoding="utf-8")
        ]
        assert not offenders, f"stale DGI cut-points still in the source: {offenders}"
