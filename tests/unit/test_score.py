"""Tests for groundlens.score dataclasses."""

from __future__ import annotations

import pytest

from groundlens._internal.thresholds import DGI_PASS, SGI_REVIEW, SGI_STRONG_PASS
from groundlens.score import DGIResult, GroundlensScore, SGIResult

# ---------------------------------------------------------------------------
# SGIResult
# ---------------------------------------------------------------------------


class TestSGIResult:
    """Tests for the SGIResult frozen dataclass."""

    def test_creation_basic(self) -> None:
        r = SGIResult(value=1.30, normalized=0.65, flagged=False, q_dist=0.8, ctx_dist=0.6)
        assert r.value == 1.30
        assert r.normalized == 0.65
        assert r.flagged is False
        assert r.q_dist == 0.8
        assert r.ctx_dist == 0.6
        assert r.method == "sgi"

    def test_frozen_immutability(self) -> None:
        r = SGIResult(value=1.30, normalized=0.65, flagged=False, q_dist=0.8, ctx_dist=0.6)
        with pytest.raises(AttributeError):
            r.value = 2.0  # type: ignore[misc]
        with pytest.raises(AttributeError):
            r.flagged = True  # type: ignore[misc]

    def test_explanation_strong_pass(self) -> None:
        r = SGIResult(
            value=SGI_STRONG_PASS + 0.1,
            normalized=0.7,
            flagged=False,
            q_dist=1.0,
            ctx_dist=0.5,
        )
        assert "strong context engagement" in r.explanation
        assert "pass" in r.explanation

    def test_explanation_partial_engagement(self) -> None:
        value = (SGI_REVIEW + SGI_STRONG_PASS) / 2  # Between review and strong pass
        r = SGIResult(value=value, normalized=0.5, flagged=False, q_dist=0.9, ctx_dist=0.8)
        assert "partial engagement" in r.explanation
        assert "review" in r.explanation.lower()

    def test_explanation_flagged_weak(self) -> None:
        r = SGIResult(
            value=SGI_REVIEW - 0.1,
            normalized=0.3,
            flagged=True,
            q_dist=0.5,
            ctx_dist=0.9,
        )
        assert "weak context engagement" in r.explanation
        assert "flagged" in r.explanation

    def test_custom_explanation_preserved(self) -> None:
        custom = "Custom explanation text"
        r = SGIResult(
            value=1.5,
            normalized=0.7,
            flagged=False,
            q_dist=1.0,
            ctx_dist=0.5,
            explanation=custom,
        )
        assert r.explanation == custom

    def test_default_method_is_sgi(self) -> None:
        r = SGIResult(value=1.0, normalized=0.5, flagged=False, q_dist=0.5, ctx_dist=0.5)
        assert r.method == "sgi"


# ---------------------------------------------------------------------------
# DGIResult
# ---------------------------------------------------------------------------


class TestDGIResult:
    """Tests for the DGIResult frozen dataclass."""

    def test_creation_basic(self) -> None:
        r = DGIResult(value=0.50, normalized=0.75, flagged=False)
        assert r.value == 0.50
        assert r.normalized == 0.75
        assert r.flagged is False
        assert r.method == "dgi"

    def test_frozen_immutability(self) -> None:
        r = DGIResult(value=0.50, normalized=0.75, flagged=False)
        with pytest.raises(AttributeError):
            r.value = 0.9  # type: ignore[misc]

    def test_explanation_pass(self) -> None:
        r = DGIResult(value=DGI_PASS + 0.1, normalized=0.7, flagged=False)
        assert "aligns with grounded patterns" in r.explanation
        assert "pass" in r.explanation

    def test_explanation_weak_alignment(self) -> None:
        r = DGIResult(value=0.15, normalized=0.575, flagged=True)
        assert "weak alignment" in r.explanation
        assert "flagged" in r.explanation

    def test_explanation_opposite_direction(self) -> None:
        r = DGIResult(value=-0.3, normalized=0.35, flagged=True)
        assert "opposes grounded direction" in r.explanation
        assert "high risk" in r.explanation

    def test_explanation_boundary_at_zero(self) -> None:
        r = DGIResult(value=0.0, normalized=0.5, flagged=True)
        assert "weak alignment" in r.explanation

    def test_explanation_boundary_at_dgi_pass(self) -> None:
        r = DGIResult(value=DGI_PASS, normalized=0.65, flagged=False)
        assert "aligns with grounded patterns" in r.explanation

    def test_custom_explanation_preserved(self) -> None:
        custom = "Custom DGI explanation"
        r = DGIResult(value=0.5, normalized=0.75, flagged=False, explanation=custom)
        assert r.explanation == custom

    def test_default_method_is_dgi(self) -> None:
        r = DGIResult(value=0.5, normalized=0.75, flagged=False)
        assert r.method == "dgi"

    def test_magnitude_default_is_zero(self) -> None:
        r = DGIResult(value=0.50, normalized=0.75, flagged=False)
        assert r.magnitude == 0.0

    def test_magnitude_stored(self) -> None:
        r = DGIResult(value=0.50, normalized=0.75, flagged=False, magnitude=0.83)
        assert r.magnitude == 0.83


# ---------------------------------------------------------------------------
# GroundlensScore
# ---------------------------------------------------------------------------


class TestGroundlensScore:
    """Tests for the GroundlensScore frozen dataclass."""

    def test_creation_with_sgi_detail(self) -> None:
        detail = SGIResult(value=1.3, normalized=0.65, flagged=False, q_dist=1.0, ctx_dist=0.7)
        score = GroundlensScore(
            value=1.3,
            normalized=0.65,
            flagged=False,
            method="sgi",
            explanation=detail.explanation,
            detail=detail,
        )
        assert score.method == "sgi"
        assert isinstance(score.detail, SGIResult)

    def test_creation_with_dgi_detail(self) -> None:
        detail = DGIResult(value=0.5, normalized=0.75, flagged=False)
        score = GroundlensScore(
            value=0.5,
            normalized=0.75,
            flagged=False,
            method="dgi",
            explanation=detail.explanation,
            detail=detail,
        )
        assert score.method == "dgi"
        assert isinstance(score.detail, DGIResult)

    def test_frozen_immutability(self) -> None:
        detail = DGIResult(value=0.5, normalized=0.75, flagged=False)
        score = GroundlensScore(
            value=0.5,
            normalized=0.75,
            flagged=False,
            method="dgi",
            explanation="test",
            detail=detail,
        )
        with pytest.raises(AttributeError):
            score.flagged = True  # type: ignore[misc]

    def test_detail_provides_method_specific_fields(self) -> None:
        detail = SGIResult(value=1.3, normalized=0.65, flagged=False, q_dist=1.0, ctx_dist=0.7)
        score = GroundlensScore(
            value=1.3,
            normalized=0.65,
            flagged=False,
            method="sgi",
            explanation="test",
            detail=detail,
        )
        assert score.detail.q_dist == 1.0  # type: ignore[union-attr]
        assert score.detail.ctx_dist == 0.7  # type: ignore[union-attr]
