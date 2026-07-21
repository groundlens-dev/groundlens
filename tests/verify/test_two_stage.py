"""Two-stage gating: stage two runs only when stage one escalates (or always=True)."""

from __future__ import annotations

import groundlens.verify.pipeline as ts_mod
from groundlens.check import Check
from groundlens.verify.detector import Verification
from groundlens.verify.pipeline import two_stage


def _sgi_check(escalate: bool) -> Check:
    return Check(
        headline="CHECK",
        label="stub",
        message="",
        level="review" if escalate else "ok",
        method="sgi",
        metric_name="Semantic Grounding Index",
        metric_abbr="SGI",
        score=1.0,
        escalate=escalate,
    )


class StubDetector:
    def __init__(self) -> None:
        self.called = False

    def verify(self, question: str, answer: str) -> Verification:
        self.called = True
        return Verification(
            check=_sgi_check(False),
            answer=answer,
            samples=("s",),
            consistency=1.0,
            method="selfcheck_nli",
            seconds=0.0,
            seed=None,
        )


def _patch_stage1(monkeypatch, escalate: bool) -> None:
    monkeypatch.setattr(ts_mod, "evaluate", lambda **kwargs: object())
    monkeypatch.setattr(ts_mod, "check", lambda score: _sgi_check(escalate))


def test_no_escalation_skips_stage_two(monkeypatch) -> None:
    _patch_stage1(monkeypatch, escalate=False)
    det = StubDetector()
    result = two_stage("Q?", "A", context="ctx", detector=det)
    assert result.escalated is False
    assert result.stage2 is None
    assert result.final is result.stage1
    assert det.called is False


def test_escalation_runs_stage_two(monkeypatch) -> None:
    _patch_stage1(monkeypatch, escalate=True)
    det = StubDetector()
    result = two_stage("Q?", "A", detector=det)
    assert result.escalated is True
    assert result.stage2 is not None
    assert det.called is True


def test_always_forces_stage_two(monkeypatch) -> None:
    _patch_stage1(monkeypatch, escalate=False)
    det = StubDetector()
    result = two_stage("Q?", "A", detector=det, always=True)
    assert result.escalated is True
    assert det.called is True
