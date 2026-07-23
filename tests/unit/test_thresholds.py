"""Tests for groundlens._internal.thresholds constants and normalization."""

from __future__ import annotations

import pytest

from groundlens._internal.thresholds import (
    DGI_PASS,
    SGI_REVIEW,
    SGI_STRONG_PASS,
    normalize_dgi,
    normalize_sgi,
)

# ---------------------------------------------------------------------------
# Threshold constant ordering
# ---------------------------------------------------------------------------


class TestThresholdConstants:
    """Verify threshold constants are correctly ordered and valued."""

    def test_sgi_strong_pass_value(self) -> None:
        assert SGI_STRONG_PASS == 1.20

    def test_sgi_review_value(self) -> None:
        assert SGI_REVIEW == 0.95

    def test_dgi_pass_value(self) -> None:
        assert DGI_PASS == 0.525

    def test_sgi_ordering(self) -> None:
        assert SGI_STRONG_PASS > SGI_REVIEW

    def test_sgi_thresholds_positive(self) -> None:
        assert SGI_STRONG_PASS > 0
        assert SGI_REVIEW > 0

    def test_dgi_threshold_in_valid_range(self) -> None:
        assert -1.0 <= DGI_PASS <= 1.0


# ---------------------------------------------------------------------------
# normalize_sgi
# ---------------------------------------------------------------------------


class TestNormalizeSgi:
    """Tests for normalize_sgi()."""

    def test_output_in_zero_one_range(self) -> None:
        for raw in [0.0, 0.3, 0.5, 0.95, 1.0, 1.2, 2.0, 5.0, 10.0]:
            result = normalize_sgi(raw)
            assert 0.0 <= result <= 1.0, f"normalize_sgi({raw}) = {result} out of range"

    def test_floor_at_0_3(self) -> None:
        """SGI <= 0.3 should map to 0.0."""
        assert normalize_sgi(0.3) == pytest.approx(0.0)
        assert normalize_sgi(0.0) == pytest.approx(0.0)
        assert normalize_sgi(-1.0) == pytest.approx(0.0)

    def test_known_mapping_review_threshold(self) -> None:
        """SGI 0.95 -> ~0.574 (tanh(0.65))."""
        result = normalize_sgi(0.95)
        assert 0.4 < result < 0.6

    def test_known_mapping_strong_pass(self) -> None:
        """SGI 1.20 -> ~0.604 (tanh(0.90))."""
        result = normalize_sgi(1.20)
        assert 0.5 < result < 0.75

    def test_known_mapping_very_strong(self) -> None:
        """SGI 2.00 -> ~0.885 (tanh(1.70))."""
        result = normalize_sgi(2.00)
        assert 0.8 < result < 0.95

    def test_monotonically_increasing(self) -> None:
        values = [0.3, 0.5, 0.8, 0.95, 1.0, 1.2, 1.5, 2.0, 3.0]
        normalized = [normalize_sgi(v) for v in values]
        for i in range(len(normalized) - 1):
            assert normalized[i] <= normalized[i + 1], (
                f"Not monotonic: normalize_sgi({values[i]})={normalized[i]} > "
                f"normalize_sgi({values[i + 1]})={normalized[i + 1]}"
            )

    def test_negative_sgi_returns_zero(self) -> None:
        assert normalize_sgi(-5.0) == pytest.approx(0.0)

    def test_very_large_sgi_approaches_one(self) -> None:
        result = normalize_sgi(100.0)
        assert result == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# normalize_dgi
# ---------------------------------------------------------------------------


class TestNormalizeDgi:
    """Tests for normalize_dgi()."""

    def test_output_in_zero_one_range(self) -> None:
        for raw in [-1.0, -0.5, 0.0, 0.3, 0.5, 1.0]:
            result = normalize_dgi(raw)
            assert 0.0 <= result <= 1.0, f"normalize_dgi({raw}) = {result} out of range"

    def test_known_mapping_minus_one(self) -> None:
        assert normalize_dgi(-1.0) == pytest.approx(0.0)

    def test_known_mapping_zero(self) -> None:
        assert normalize_dgi(0.0) == pytest.approx(0.5)

    def test_known_mapping_pass_threshold(self) -> None:
        assert normalize_dgi(0.3) == pytest.approx(0.65)

    def test_known_mapping_one(self) -> None:
        assert normalize_dgi(1.0) == pytest.approx(1.0)

    def test_monotonically_increasing(self) -> None:
        values = [-1.0, -0.5, 0.0, 0.3, 0.5, 1.0]
        normalized = [normalize_dgi(v) for v in values]
        for i in range(len(normalized) - 1):
            assert normalized[i] < normalized[i + 1]

    def test_clamped_below_minus_one(self) -> None:
        assert normalize_dgi(-2.0) == pytest.approx(0.0)

    def test_clamped_above_one(self) -> None:
        assert normalize_dgi(2.0) == pytest.approx(1.0)

    def test_linear_relationship(self) -> None:
        """normalize_dgi is (raw + 1) / 2 clamped to [0, 1]."""
        for raw in [-0.8, -0.3, 0.1, 0.6, 0.9]:
            expected = (raw + 1.0) / 2.0
            assert normalize_dgi(raw) == pytest.approx(expected)
