"""Tests for the canonical check layer (groundlens.check)."""

from __future__ import annotations

import pytest

from groundlens.check import (
    HEADLINE,
    Check,
    check,
    check_for_dgi,
    check_for_sgi,
)
from groundlens.score import DGIResult, GroundlensScore, SGIResult

# ---------------------------------------------------------------------------
# SGI checks — levels come from calibrated thresholds (1.20 / 0.95)
# ---------------------------------------------------------------------------


class TestSGICheck:
    def test_supported(self) -> None:
        r = SGIResult(value=2.44, normalized=0.9, flagged=False, q_dist=1.1, ctx_dist=0.45)
        v = check_for_sgi(r)
        assert v.level == "ok"
        assert v.label == "Supported by the document"
        assert v.method == "sgi"
        assert v.metric_abbr == "SGI"

    def test_partly_supported(self) -> None:
        r = SGIResult(value=1.05, normalized=0.6, flagged=False, q_dist=0.8, ctx_dist=0.76)
        v = check_for_sgi(r)
        assert v.level == "review"
        assert v.label == "Partly supported"

    def test_not_supported(self) -> None:
        r = SGIResult(value=0.76, normalized=0.4, flagged=True, q_dist=0.5, ctx_dist=0.66)
        v = check_for_sgi(r)
        assert v.level == "risk"
        assert v.label == "Not supported by the document"

    def test_boundary_strong_pass_is_supported(self) -> None:
        r = SGIResult(value=1.20, normalized=0.6, flagged=False, q_dist=1.0, ctx_dist=0.83)
        assert check_for_sgi(r).level == "ok"

    def test_boundary_review_is_partly(self) -> None:
        r = SGIResult(value=0.95, normalized=0.45, flagged=False, q_dist=0.9, ctx_dist=0.95)
        assert check_for_sgi(r).level == "review"

    def test_detail_has_both_distances(self) -> None:
        r = SGIResult(value=2.0, normalized=0.88, flagged=False, q_dist=1.2, ctx_dist=0.6)
        v = check_for_sgi(r)
        assert "0.60" in v.detail  # ctx_dist
        assert "1.20" in v.detail  # q_dist

    def test_no_jargon_in_label(self) -> None:
        r = SGIResult(value=0.5, normalized=0.2, flagged=True, q_dist=0.4, ctx_dist=0.9)
        v = check_for_sgi(r)
        assert "hallucinat" not in v.label.lower()
        assert "grounding" not in v.label.lower()


# ---------------------------------------------------------------------------
# DGI checks — single binary cut at 0.30 (grounded / not grounded)
# ---------------------------------------------------------------------------


class TestDGICheck:
    def test_looks_grounded(self) -> None:
        r = DGIResult(value=0.62, normalized=0.81, flagged=False, magnitude=1.02)
        v = check_for_dgi(r)
        assert v.level == "ok"
        assert v.label == "Looks grounded"
        assert v.metric_abbr == "DGI"

    def test_below_cut_not_grounded(self) -> None:
        r = DGIResult(value=0.20, normalized=0.60, flagged=True, magnitude=0.7)
        v = check_for_dgi(r)
        assert v.level == "risk"
        assert v.label == "Not grounded"

    def test_not_grounded(self) -> None:
        r = DGIResult(value=-0.12, normalized=0.44, flagged=True, magnitude=0.9)
        v = check_for_dgi(r)
        assert v.level == "risk"
        assert v.label == "Not grounded"

    def test_note_mentions_no_source(self) -> None:
        r = DGIResult(value=0.62, normalized=0.81, flagged=False, magnitude=1.0)
        assert "No source" in check_for_dgi(r).note

    def test_detail_uses_magnitude(self) -> None:
        r = DGIResult(value=0.41, normalized=0.7, flagged=False, magnitude=1.23)
        assert "1.23" in check_for_dgi(r).detail


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestCheckRender:
    def test_line_format(self) -> None:
        r = SGIResult(value=2.44, normalized=0.9, flagged=False, q_dist=1.1, ctx_dist=0.45)
        line = check_for_sgi(r).line()
        assert line == ("CHECK: Supported by the document (Semantic Grounding Index - SGI=2.44)")

    def test_two_decimals(self) -> None:
        r = DGIResult(value=0.4137, normalized=0.7, flagged=False, magnitude=1.0)
        assert "DGI=0.41" in check_for_dgi(r).line()

    def test_render_includes_message_and_note(self) -> None:
        r = DGIResult(value=0.41, normalized=0.7, flagged=False, magnitude=1.0)
        out = check_for_dgi(r).render()
        assert "CHECK:" in out
        assert "No source given" in out

    def test_str_equals_render(self) -> None:
        r = SGIResult(value=2.0, normalized=0.88, flagged=False, q_dist=1.2, ctx_dist=0.6)
        v = check_for_sgi(r)
        assert str(v) == v.render()

    def test_headline_constant(self) -> None:
        assert HEADLINE == "CHECK"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class TestCheckDispatch:
    def test_dispatch_sgi(self) -> None:
        r = SGIResult(value=2.0, normalized=0.88, flagged=False, q_dist=1.2, ctx_dist=0.6)
        assert check(r).method == "sgi"

    def test_dispatch_dgi(self) -> None:
        r = DGIResult(value=0.41, normalized=0.7, flagged=False, magnitude=1.0)
        assert check(r).method == "dgi"

    def test_dispatch_groundlens_score(self) -> None:
        detail = SGIResult(value=1.3, normalized=0.65, flagged=False, q_dist=1.0, ctx_dist=0.7)
        score = GroundlensScore(
            value=1.3,
            normalized=0.65,
            flagged=False,
            method="sgi",
            explanation=detail.explanation,
            detail=detail,
        )
        assert check(score).method == "sgi"
        assert isinstance(check(score), Check)

    def test_dispatch_bad_type_raises(self) -> None:
        with pytest.raises(TypeError, match="SGIResult, DGIResult, or GroundlensScore"):
            check("not a result")  # type: ignore[arg-type]
