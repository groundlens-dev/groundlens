"""Unit tests for DGI and SGI input validation and edge cases.

These tests verify ValueError on empty inputs and class initialization
without loading the embedding model.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from groundlens.dgi import (
    DGI,
    _compute_reference_direction,
    _get_mu_hat,
    _mu_hat_cache,
    compute_dgi,
    reset_calibration_cache,
)
from groundlens.sgi import SGI, compute_sgi

# ---------------------------------------------------------------------------
# DGI input validation
# ---------------------------------------------------------------------------


class TestDGIValidation:
    """Test compute_dgi input validation (no model loaded)."""

    def test_empty_question_raises(self) -> None:
        with pytest.raises(ValueError, match="question"):
            compute_dgi(question="", response="Some answer.")

    def test_whitespace_question_raises(self) -> None:
        with pytest.raises(ValueError, match="question"):
            compute_dgi(question="   ", response="Some answer.")

    def test_empty_response_raises(self) -> None:
        with pytest.raises(ValueError, match="response"):
            compute_dgi(question="What is X?", response="")

    def test_whitespace_response_raises(self) -> None:
        with pytest.raises(ValueError, match="response"):
            compute_dgi(question="What is X?", response="  \t  ")


# ---------------------------------------------------------------------------
# SGI input validation
# ---------------------------------------------------------------------------


class TestSGIValidation:
    """Test compute_sgi input validation (no model loaded)."""

    def test_empty_question_raises(self) -> None:
        with pytest.raises(ValueError, match="question"):
            compute_sgi(question="", context="C.", response="A.")

    def test_empty_context_raises(self) -> None:
        with pytest.raises(ValueError, match="context"):
            compute_sgi(question="Q?", context="", response="A.")

    def test_empty_response_raises(self) -> None:
        with pytest.raises(ValueError, match="response"):
            compute_sgi(question="Q?", context="C.", response="")

    def test_whitespace_context_raises(self) -> None:
        with pytest.raises(ValueError, match="context"):
            compute_sgi(question="Q?", context="   ", response="A.")


# ---------------------------------------------------------------------------
# reset_calibration_cache
# ---------------------------------------------------------------------------


class TestResetCache:
    """Test the calibration cache reset function."""

    def test_reset_clears_cache(self) -> None:

        # Insert a fake entry
        _mu_hat_cache[("test", "key")] = np.zeros(3, dtype=np.float32)
        assert len(_mu_hat_cache) > 0

        reset_calibration_cache()
        assert len(_mu_hat_cache) == 0


# ---------------------------------------------------------------------------
# DGI class validation
# ---------------------------------------------------------------------------


class TestDGIClass:
    """Test DGI class initialization and calibrate() validation."""

    def test_init_stores_params(self) -> None:
        dgi = DGI(model="test-model", reference_csv="test.csv")
        assert dgi.model == "test-model"
        assert dgi.reference_csv == "test.csv"

    def test_calibrate_no_args_raises(self) -> None:
        dgi = DGI()
        with pytest.raises(ValueError, match="Provide either"):
            dgi.calibrate()

    def test_calibrate_csv_path_updates_ref(self) -> None:
        dgi = DGI()
        dgi.calibrate(csv_path="domain.csv")
        assert dgi.reference_csv == "domain.csv"


# ---------------------------------------------------------------------------
# SGI class
# ---------------------------------------------------------------------------


class TestSGIClass:
    """Test SGI class initialization."""

    def test_init_stores_model(self) -> None:
        sgi = SGI(model="custom-model")
        assert sgi.model == "custom-model"

    def test_default_model(self) -> None:
        from groundlens._internal.embeddings import DEFAULT_MODEL

        sgi = SGI()
        assert sgi.model == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# DGI degenerate cases (mocked embeddings)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DGI internals (mocked embeddings)
# ---------------------------------------------------------------------------


class TestComputeReferenceDirection:
    """Test _compute_reference_direction with mocked embeddings."""

    @patch("groundlens.dgi.encode_texts")
    def test_returns_unit_vector(self, mock_encode) -> None:
        rng = np.random.default_rng(42)
        # 5 pairs → 10 texts
        mock_encode.return_value = rng.standard_normal((10, 384)).astype(np.float32)

        pairs = [("Q?", "A.") for _ in range(5)]
        mu = _compute_reference_direction(pairs, "mock-model")
        norm = float(np.linalg.norm(mu))
        assert norm == pytest.approx(1.0, abs=1e-5)

    @patch("groundlens.dgi.encode_texts")
    def test_zero_displacement_raises(self, mock_encode) -> None:
        # All identical vectors → zero displacement → should raise
        vec = np.ones((10, 384), dtype=np.float32) * 0.5
        mock_encode.return_value = vec

        pairs = [("Q?", "A.") for _ in range(5)]
        # Displacement is zero for each pair since q and r embed identically
        # But unit_normalize returns zero for zero vectors, so no valid
        # displacements → should raise ValueError
        with pytest.raises(ValueError, match="No valid displacement"):
            _compute_reference_direction(pairs, "mock-model")


class TestGetMuHat:
    """Test _get_mu_hat caching."""

    @patch("groundlens.dgi._compute_reference_direction")
    @patch("groundlens.dgi.load_reference_pairs")
    def test_caches_result(self, mock_loader, mock_compute) -> None:
        reset_calibration_cache()
        mock_loader.return_value = [("Q?", "A.")]
        fake_mu = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        mock_compute.return_value = fake_mu

        result1 = _get_mu_hat("test-model", None)
        result2 = _get_mu_hat("test-model", None)

        # Should only compute once (cached)
        mock_compute.assert_called_once()
        np.testing.assert_array_equal(result1, result2)
        reset_calibration_cache()

    @patch("groundlens.dgi._compute_reference_direction")
    @patch("groundlens.dgi.load_reference_pairs")
    def test_different_csv_separate_cache(self, mock_loader, mock_compute) -> None:
        reset_calibration_cache()
        mock_loader.return_value = [("Q?", "A.")]
        fake_mu = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        mock_compute.return_value = fake_mu

        _get_mu_hat("test-model", "a.csv")
        _get_mu_hat("test-model", "b.csv")

        # Different CSV paths → computed twice
        assert mock_compute.call_count == 2
        reset_calibration_cache()


# ---------------------------------------------------------------------------
# DGI compute_dgi happy path (mocked)
# ---------------------------------------------------------------------------


class TestComputeDGIMocked:
    """Test compute_dgi with mocked embeddings and reference direction."""

    @patch("groundlens.dgi._get_mu_hat")
    @patch("groundlens.dgi.encode_texts")
    def test_aligned_response_not_flagged(
        self,
        mock_encode,
        mock_mu,
    ) -> None:
        # Reference direction points along [1, 0, 0]
        mock_mu.return_value = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        # Question at origin, response displaced along reference direction
        q = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        r = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        mock_encode.return_value = np.stack([q, r])

        result = compute_dgi(question="Q?", response="A.")
        assert result.flagged is False
        assert result.value == pytest.approx(1.0, abs=0.01)

    @patch("groundlens.dgi._get_mu_hat")
    @patch("groundlens.dgi.encode_texts")
    def test_perpendicular_response_flagged(
        self,
        mock_encode,
        mock_mu,
    ) -> None:
        mock_mu.return_value = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        q = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        r = np.array([0.0, 1.0, 0.0], dtype=np.float32)  # perpendicular
        mock_encode.return_value = np.stack([q, r])

        result = compute_dgi(question="Q?", response="A.")
        assert result.flagged is True
        assert result.value == pytest.approx(0.0, abs=0.01)

    @patch("groundlens.dgi._get_mu_hat")
    @patch("groundlens.dgi.encode_texts")
    def test_opposite_response_high_risk(
        self,
        mock_encode,
        mock_mu,
    ) -> None:
        mock_mu.return_value = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        q = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        r = np.array([-1.0, 0.0, 0.0], dtype=np.float32)  # opposite
        mock_encode.return_value = np.stack([q, r])

        result = compute_dgi(question="Q?", response="A.")
        assert result.flagged is True
        assert result.value < 0.0


class TestDGIDegenerate:
    """Test DGI with degenerate inputs using mocked embeddings."""

    @patch("groundlens.dgi._get_mu_hat")
    @patch("groundlens.dgi.encode_texts")
    def test_identical_question_response_flagged(
        self,
        mock_encode,
        mock_mu,
    ) -> None:
        # Response identical to question → zero displacement → flagged
        vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        mock_encode.return_value = np.stack([vec, vec])
        mock_mu.return_value = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        result = compute_dgi(question="Q?", response="A.")
        assert result.flagged is True
        assert result.value == 0.0


# ---------------------------------------------------------------------------
# SGI degenerate cases (mocked embeddings)
# ---------------------------------------------------------------------------


class TestSGIDegenerate:
    """Test SGI with degenerate inputs using mocked embeddings."""

    @patch("groundlens.sgi.encode_texts")
    def test_response_identical_to_context_passes(
        self,
        mock_encode,
    ) -> None:
        q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        ctx = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        resp = ctx.copy()  # identical to context
        mock_encode.return_value = np.stack([q, ctx, resp])

        result = compute_sgi(question="Q?", context="C.", response="A.")
        assert result.flagged is False
        assert result.value == 10.0  # degenerate case returns 10.0

    @patch("groundlens.sgi.encode_texts")
    def test_response_identical_to_question_flagged(
        self,
        mock_encode,
    ) -> None:
        q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        ctx = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        resp = q.copy()  # identical to question
        mock_encode.return_value = np.stack([q, ctx, resp])

        result = compute_sgi(question="Q?", context="C.", response="A.")
        assert result.flagged is True
        assert result.value == 0.0
