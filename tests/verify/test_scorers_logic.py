"""Scorer aggregation logic, exercised with stubs (no model download).

The parts that load a real NLI model (``NLIScorer._ensure_loaded`` /
``_contradiction``) are marked ``# pragma: no cover`` in the source: they only run
against a downloaded model, which CI does not do. Everything else — the mean, the
empty-sample guard, the cosine math — is pure logic and is tested here.
"""

from __future__ import annotations

import numpy as np
import pytest

from groundlens.verify.scorers import EmbeddingScorer, NLIScorer


def test_nli_inconsistency_is_mean_contradiction(monkeypatch: pytest.MonkeyPatch) -> None:
    scorer = NLIScorer()
    # Stand in for the real NLI forward pass: return fixed contradiction probs.
    monkeypatch.setattr(scorer, "_contradiction", lambda premises, hypotheses: [0.1, 0.9])
    assert scorer.inconsistency("q", "a", ["s1", "s2"]) == pytest.approx(0.5)


def test_nli_inconsistency_no_usable_samples_returns_one() -> None:
    scorer = NLIScorer()
    assert scorer.inconsistency("q", "a", []) == 1.0
    assert scorer.inconsistency("q", "a", ["", "   "]) == 1.0
    assert scorer.inconsistency("q", "", ["s1"]) == 1.0


def test_nli_constructor_records_config() -> None:
    scorer = NLIScorer(model="some/mnli", device="cpu", max_length=128, batch_size=8)
    assert scorer.model_name == "some/mnli"
    assert scorer.device == "cpu"
    assert scorer.max_length == 128
    assert scorer.batch_size == 8


def test_embedding_inconsistency_is_mean_cosine_disagreement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import groundlens._internal.embeddings as emb

    # answer == first sample (cosine 1 -> 0 disagreement); orthogonal to second (-> 1).
    vecs = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    monkeypatch.setattr(emb, "encode_texts", lambda texts, encoder=None: vecs)

    scorer = EmbeddingScorer()
    assert scorer.inconsistency("q", "a", ["s1", "s2"]) == pytest.approx(0.5)


def test_embedding_inconsistency_no_usable_samples_returns_one() -> None:
    scorer = EmbeddingScorer()
    assert scorer.inconsistency("q", "a", []) == 1.0
    assert scorer.inconsistency("q", "", ["s1"]) == 1.0
