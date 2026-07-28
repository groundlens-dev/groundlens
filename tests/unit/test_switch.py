"""Unit tests for groundlens.switch.GroundingSwitch."""

from __future__ import annotations

import pytest

from groundlens.check import Check, check_for_dgi, check_for_sgi, check_for_verification
from groundlens.score import DGIResult, GroundlensScore, SGIResult
from groundlens.switch import GroundingSwitch, SwitchAction, SwitchDecision

# ── Helpers ─────────────────────────────────────────────────────────────────


def _sgi(value: float, *, flagged: bool | None = None) -> SGIResult:
    if flagged is None:
        flagged = value < 0.95
    return SGIResult(
        value=value,
        normalized=min(1.0, max(0.0, value / 2.0)),
        flagged=flagged,
        q_dist=1.0,
        ctx_dist=1.0 / value if value > 0 else 99.0,
    )


def _dgi(value: float, *, flagged: bool | None = None) -> DGIResult:
    if flagged is None:
        flagged = value < 0.525
    return DGIResult(
        value=value,
        normalized=(value + 1.0) / 2.0,
        flagged=flagged,
        magnitude=0.5,
    )


def _groundlens_score(detail: SGIResult | DGIResult) -> GroundlensScore:
    return GroundlensScore(
        value=detail.value,
        normalized=detail.normalized,
        flagged=detail.flagged,
        method=detail.method,
        explanation=detail.explanation,
        detail=detail,
    )


# ── Construction ────────────────────────────────────────────────────────────


class TestGroundingSwitchInit:
    def test_defaults(self):
        sw = GroundingSwitch()
        assert sw.accept_threshold_sgi == 1.20
        assert sw.reject_threshold_sgi == 0.95
        assert sw.accept_threshold_dgi == 0.525
        assert sw.on_reject is SwitchAction.FALLBACK

    def test_custom_thresholds(self):
        sw = GroundingSwitch(
            accept_threshold_sgi=1.5,
            reject_threshold_sgi=1.0,
            accept_threshold_dgi=0.6,
            on_reject="reject",
        )
        assert sw.accept_threshold_sgi == 1.5
        assert sw.reject_threshold_sgi == 1.0
        assert sw.accept_threshold_dgi == 0.6
        assert sw.on_reject is SwitchAction.REJECT

    def test_on_reject_accepts_enum(self):
        sw = GroundingSwitch(on_reject=SwitchAction.REGENERATE)
        assert sw.on_reject is SwitchAction.REGENERATE

    def test_on_reject_case_insensitive_string(self):
        sw = GroundingSwitch(on_reject="Escalate")
        assert sw.on_reject is SwitchAction.ESCALATE

    def test_invalid_on_reject_raises(self):
        with pytest.raises(ValueError, match="on_reject must be one of"):
            GroundingSwitch(on_reject="delete_everything")

    def test_inverted_sgi_thresholds_raise(self):
        with pytest.raises(ValueError, match="reject_threshold_sgi"):
            GroundingSwitch(accept_threshold_sgi=0.8, reject_threshold_sgi=1.2)


# ── SGI decisions ───────────────────────────────────────────────────────────


class TestSwitchSGI:
    def test_strong_pass_accepts(self):
        sw = GroundingSwitch()
        decision = sw.decide(_sgi(1.50))
        assert decision.action is SwitchAction.ACCEPT
        assert decision.write_to_state is True
        assert decision.method == "sgi"
        assert decision.level == "ok"
        assert "safe to write" in decision.reason

    def test_exact_accept_threshold_accepts(self):
        sw = GroundingSwitch()
        decision = sw.decide(_sgi(1.20))
        assert decision.action is SwitchAction.ACCEPT
        assert decision.write_to_state is True

    def test_uncertain_band_escalates(self):
        sw = GroundingSwitch()
        decision = sw.decide(_sgi(1.05))
        assert decision.action is SwitchAction.ESCALATE
        assert decision.write_to_state is False
        assert decision.level == "review"
        assert "uncertain" in decision.reason

    def test_below_reject_threshold_fallback_by_default(self):
        sw = GroundingSwitch()
        decision = sw.decide(_sgi(0.70))
        assert decision.action is SwitchAction.FALLBACK
        assert decision.write_to_state is False
        assert decision.level == "risk"

    def test_on_reject_reject(self):
        sw = GroundingSwitch(on_reject="reject")
        decision = sw.decide(_sgi(0.50))
        assert decision.action is SwitchAction.REJECT
        assert decision.write_to_state is False

    def test_on_reject_regenerate(self):
        sw = GroundingSwitch(on_reject="regenerate")
        decision = sw.decide(_sgi(0.50))
        assert decision.action is SwitchAction.REGENERATE
        assert decision.write_to_state is False

    def test_on_reject_escalate(self):
        sw = GroundingSwitch(on_reject="escalate")
        decision = sw.decide(_sgi(0.50))
        assert decision.action is SwitchAction.ESCALATE
        assert decision.write_to_state is False

    def test_boundary_just_below_accept(self):
        sw = GroundingSwitch()
        decision = sw.decide(_sgi(1.199))
        assert decision.action is SwitchAction.ESCALATE

    def test_boundary_just_below_reject(self):
        sw = GroundingSwitch()
        decision = sw.decide(_sgi(0.949))
        assert decision.action is SwitchAction.FALLBACK


# ── DGI decisions ───────────────────────────────────────────────────────────


class TestSwitchDGI:
    def test_pass_accepts(self):
        sw = GroundingSwitch()
        decision = sw.decide(_dgi(0.70))
        assert decision.action is SwitchAction.ACCEPT
        assert decision.write_to_state is True
        assert decision.method == "dgi"
        assert decision.level == "ok"

    def test_exact_threshold_accepts(self):
        sw = GroundingSwitch()
        decision = sw.decide(_dgi(0.525))
        assert decision.action is SwitchAction.ACCEPT
        assert decision.write_to_state is True

    def test_below_threshold_fallback(self):
        sw = GroundingSwitch()
        decision = sw.decide(_dgi(0.30))
        assert decision.action is SwitchAction.FALLBACK
        assert decision.write_to_state is False
        assert decision.level == "risk"

    def test_negative_dgi_fallback(self):
        sw = GroundingSwitch()
        decision = sw.decide(_dgi(-0.20))
        assert decision.action is SwitchAction.FALLBACK
        assert decision.write_to_state is False

    def test_custom_dgi_threshold(self):
        sw = GroundingSwitch(accept_threshold_dgi=0.60)
        assert sw.decide(_dgi(0.55)).action is SwitchAction.FALLBACK
        assert sw.decide(_dgi(0.60)).action is SwitchAction.ACCEPT


# ── Input coercion ──────────────────────────────────────────────────────────


class TestSwitchCoercion:
    def test_accepts_sgi_result(self):
        sw = GroundingSwitch()
        decision = sw.decide(_sgi(1.5))
        assert isinstance(decision, SwitchDecision)
        assert decision.method == "sgi"

    def test_accepts_dgi_result(self):
        sw = GroundingSwitch()
        decision = sw.decide(_dgi(0.7))
        assert decision.method == "dgi"

    def test_accepts_groundlens_score_sgi(self):
        sw = GroundingSwitch()
        gs = _groundlens_score(_sgi(1.5))
        decision = sw.decide(gs)
        assert decision.action is SwitchAction.ACCEPT
        assert decision.method == "sgi"

    def test_accepts_groundlens_score_dgi(self):
        sw = GroundingSwitch()
        gs = _groundlens_score(_dgi(0.2))
        decision = sw.decide(gs)
        assert decision.action is SwitchAction.FALLBACK
        assert decision.method == "dgi"

    def test_accepts_check_sgi(self):
        sw = GroundingSwitch()
        chk = check_for_sgi(_sgi(1.5))
        decision = sw.decide(chk)
        assert decision.action is SwitchAction.ACCEPT
        assert decision.check is chk

    def test_accepts_check_dgi(self):
        sw = GroundingSwitch()
        chk = check_for_dgi(_dgi(0.1))
        decision = sw.decide(chk)
        assert decision.action is SwitchAction.FALLBACK

    def test_non_geometric_check_escalates(self):
        """Consistency (SC) Checks are not geometry — Switch escalates."""
        sw = GroundingSwitch()
        chk = check_for_verification(0.90, method="selfcheck_nli", n_samples=5)
        decision = sw.decide(chk)
        assert decision.action is SwitchAction.ESCALATE
        assert decision.write_to_state is False
        assert "Non-geometric" in decision.reason

    def test_unknown_type_raises(self):
        sw = GroundingSwitch()
        with pytest.raises(TypeError, match="expects SGIResult"):
            sw.decide("not a score")  # type: ignore[arg-type]


# ── Callable interface + decision shape ─────────────────────────────────────


class TestSwitchCallableAndDecision:
    def test_callable_alias(self):
        sw = GroundingSwitch()
        decision = sw(_sgi(1.5))
        assert decision.action is SwitchAction.ACCEPT

    def test_decision_str(self):
        sw = GroundingSwitch()
        decision = sw.decide(_sgi(1.5))
        text = str(decision)
        assert "accept" in text
        assert "write_to_state=True" in text
        assert "sgi=" in text

    def test_decision_carries_check(self):
        sw = GroundingSwitch()
        decision = sw.decide(_sgi(1.5))
        assert isinstance(decision.check, Check)
        assert decision.check.level == "ok"
        assert decision.check.method == "sgi"

    def test_write_to_state_only_on_accept(self):
        sw = GroundingSwitch(on_reject="reject")
        assert sw.decide(_sgi(1.5)).write_to_state is True
        assert sw.decide(_sgi(1.05)).write_to_state is False
        assert sw.decide(_sgi(0.5)).write_to_state is False


# ── Action enum ─────────────────────────────────────────────────────────────


class TestSwitchAction:
    def test_values_are_lowercase_strings(self):
        assert SwitchAction.ACCEPT.value == "accept"
        assert SwitchAction.REJECT.value == "reject"
        assert SwitchAction.FALLBACK.value == "fallback"
        assert SwitchAction.REGENERATE.value == "regenerate"
        assert SwitchAction.ESCALATE.value == "escalate"

    def test_str_enum_compares_to_string(self):
        assert SwitchAction.ACCEPT == "accept"
