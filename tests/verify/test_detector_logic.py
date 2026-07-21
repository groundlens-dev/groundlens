"""Detector wiring: returns a Check, maps consistency, names the method, validates args."""

from __future__ import annotations

import pytest

from groundlens.check import Check
from groundlens.verify.detector import SampleConsistency, Verification


class StubGen:
    def generate(self, prompt: str, n: int = 1) -> list[str]:
        if "Rewrite" in prompt:
            return ["1. a?\n2. b?\n3. c?"]
        return ["Madrid" for _ in range(n)]

    def generate_many(self, prompts: list[str]) -> list[str]:
        return ["Madrid" for _ in prompts]


class StubScorer:
    def __init__(self, value: float) -> None:
        self.value = value

    def inconsistency(self, question: str, answer: str, samples: list[str]) -> float:
        return self.value


def test_consistent_answer_is_ok() -> None:
    det = SampleConsistency(
        generator=StubGen(), sampler="resample", scorer=StubScorer(0.0), n_samples=5
    )
    v = det.verify("What is the capital of Spain?", "Madrid")
    assert isinstance(v, Verification)
    assert isinstance(v.check, Check)
    assert v.consistency == 1.0
    assert v.check.level == "ok"
    assert v.method.startswith("selfcheck_")
    assert len(v.samples) == 5


def test_inconsistent_answer_escalates() -> None:
    det = SampleConsistency(
        generator=StubGen(), sampler="paraphrase", scorer=StubScorer(1.0), n_samples=3
    )
    v = det.verify("Q?", "Madrid")
    assert v.consistency == 0.0
    assert v.check.level == "risk"
    assert v.check.escalate is True
    assert v.method.startswith("paraphrase_")


def test_check_shortcut_returns_check() -> None:
    det = SampleConsistency(generator=StubGen(), scorer=StubScorer(0.0))
    assert isinstance(det.check("Q?", "Madrid"), Check)


def test_requires_model_or_generator() -> None:
    with pytest.raises(ValueError, match=r"model=|generator="):
        SampleConsistency(sampler="resample", scorer=StubScorer(0.0))


def test_rejects_unknown_sampler() -> None:
    with pytest.raises(ValueError, match="sampler"):
        SampleConsistency(generator=StubGen(), sampler="nope", scorer=StubScorer(0.0))
