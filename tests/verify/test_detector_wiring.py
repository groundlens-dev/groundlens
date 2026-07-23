"""Detector wiring: scorer selection, generator selection, presets, validation.

All instantiation-only (no model loads): building an ``NLIScorer`` or an
``HFTextGenerator`` does not download anything; loading is lazy.
"""

from __future__ import annotations

import pytest

from groundlens.providers.hf import HFTextGenerator
from groundlens.verify.detector import ParaphraseCheck, SampleConsistency, SelfCheckNLI
from groundlens.verify.scorers import EmbeddingScorer, NLIScorer


class _StubGen:
    def generate(self, prompt: str, n: int = 1) -> list[str]:
        return [f"s{i}" for i in range(n)]

    def generate_many(self, prompts: list[str]) -> list[str]:
        return [f"m{i}" for i in range(len(prompts))]


def test_scorer_string_nli() -> None:
    sc = SampleConsistency(generator=_StubGen(), scorer="nli")
    assert isinstance(sc._scorer, NLIScorer)


def test_scorer_string_embedding() -> None:
    sc = SampleConsistency(generator=_StubGen(), scorer="embedding")
    assert isinstance(sc._scorer, EmbeddingScorer)


def test_scorer_string_invalid_raises() -> None:
    with pytest.raises(ValueError, match="scorer must be"):
        SampleConsistency(generator=_StubGen(), scorer="nope")


def test_custom_scorer_object_is_used() -> None:
    class MyScorer:
        name = "custom"

        def inconsistency(self, question: str, answer: str, samples: list[str]) -> float:
            return 0.0

    sc = SampleConsistency(generator=_StubGen(), scorer=MyScorer())
    assert sc._method.endswith("custom")


def test_invalid_sampler_raises() -> None:
    with pytest.raises(ValueError, match="sampler must be"):
        SampleConsistency(generator=_StubGen(), sampler="nope")


def test_model_builds_local_generator_without_loading() -> None:
    sc = SampleConsistency(model="fake/model", scorer="embedding")
    assert isinstance(sc._generator, HFTextGenerator)
    assert sc._generator._model is None  # still lazy


def test_requires_model_or_generator() -> None:
    with pytest.raises(ValueError, match="Provide either"):
        SampleConsistency(scorer="embedding")


def test_presets_construct() -> None:
    assert SelfCheckNLI(generator=_StubGen())._method == "selfcheck_nli"
    assert ParaphraseCheck(generator=_StubGen())._method == "paraphrase_nli"


def test_verify_end_to_end_with_stubs() -> None:
    class ZeroScorer:
        def inconsistency(self, question: str, answer: str, samples: list[str]) -> float:
            return 0.0  # perfectly consistent

    sc = SampleConsistency(generator=_StubGen(), scorer=ZeroScorer(), n_samples=3)
    v = sc.verify("Who wrote Hamlet?", "Shakespeare")
    assert v.consistency == 1.0
    assert v.answer == "Shakespeare"
    assert len(v.samples) == 3
    assert v.check.level == "ok"
    assert sc.check("Who wrote Hamlet?", "Shakespeare").level == "ok"
