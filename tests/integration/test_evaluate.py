"""Integration tests for groundlens.evaluate module.

Tests the high-level evaluate() and evaluate_batch() functions with
real embeddings.
"""

from __future__ import annotations

import pytest

from groundlens.evaluate import evaluate, evaluate_batch
from groundlens.score import DGIResult, SGIResult

pytestmark = pytest.mark.slow


class TestEvaluateAutoSelect:
    """Test that evaluate() auto-selects SGI with context, DGI without."""

    def test_with_context_uses_sgi(self, grounded_triple: dict[str, str]) -> None:
        score = evaluate(
            question=grounded_triple["question"],
            response=grounded_triple["response"],
            context=grounded_triple["context"],
        )
        assert score.method == "sgi"
        assert isinstance(score.detail, SGIResult)

    def test_without_context_uses_dgi(self, factual_pair: dict[str, str]) -> None:
        score = evaluate(
            question=factual_pair["question"],
            response=factual_pair["response"],
        )
        assert score.method == "dgi"
        assert isinstance(score.detail, DGIResult)

    def test_with_none_context_uses_dgi(self, factual_pair: dict[str, str]) -> None:
        score = evaluate(
            question=factual_pair["question"],
            response=factual_pair["response"],
            context=None,
        )
        assert score.method == "dgi"

    def test_with_empty_string_context_uses_dgi(self, factual_pair: dict[str, str]) -> None:
        score = evaluate(
            question=factual_pair["question"],
            response=factual_pair["response"],
            context="",
        )
        assert score.method == "dgi"

    def test_with_whitespace_context_uses_dgi(self, factual_pair: dict[str, str]) -> None:
        score = evaluate(
            question=factual_pair["question"],
            response=factual_pair["response"],
            context="   ",
        )
        assert score.method == "dgi"


class TestEvaluateScoreFields:
    """Test that GroundlensScore fields are populated."""

    def test_all_fields_present_sgi(self, grounded_triple: dict[str, str]) -> None:
        score = evaluate(
            question=grounded_triple["question"],
            response=grounded_triple["response"],
            context=grounded_triple["context"],
        )
        assert score.value is not None
        assert 0.0 <= score.normalized <= 1.0
        assert isinstance(score.flagged, bool)
        assert score.method in ("sgi", "dgi")
        assert len(score.explanation) > 0
        assert score.detail is not None

    def test_all_fields_present_dgi(self, factual_pair: dict[str, str]) -> None:
        score = evaluate(
            question=factual_pair["question"],
            response=factual_pair["response"],
        )
        assert score.value is not None
        assert 0.0 <= score.normalized <= 1.0
        assert isinstance(score.flagged, bool)
        assert score.method == "dgi"
        assert len(score.explanation) > 0


class TestEvaluateBatch:
    """Test evaluate_batch()."""

    def test_batch_returns_list(self) -> None:
        items = [
            {
                "question": "What is the capital of France?",
                "response": "The capital of France is Paris.",
                "context": "France is in Western Europe. Its capital is Paris.",
            },
            {
                "question": "What causes gravity?",
                "response": "Gravity is caused by the curvature of spacetime.",
            },
        ]
        results = evaluate_batch(items)
        assert len(results) == 2

    def test_batch_first_uses_sgi_second_uses_dgi(self) -> None:
        items = [
            {
                "question": "What is X?",
                "response": "X is Y.",
                "context": "According to the manual, X is Y.",
            },
            {
                "question": "What is Z?",
                "response": "Z is W.",
            },
        ]
        results = evaluate_batch(items)
        assert results[0].method == "sgi"
        assert results[1].method == "dgi"

    def test_batch_empty_list(self) -> None:
        results = evaluate_batch([])
        assert results == []

    def test_batch_single_item(self) -> None:
        items = [
            {
                "question": "What is the Sun?",
                "response": "The Sun is a star at the center of our solar system.",
            },
        ]
        results = evaluate_batch(items)
        assert len(results) == 1


class TestEvaluateBatchErrors:
    """Test error handling in evaluate_batch()."""

    def test_missing_question_raises_key_error(self) -> None:
        items = [{"response": "Some answer."}]
        with pytest.raises(KeyError, match="question"):
            evaluate_batch(items)

    def test_missing_response_raises_key_error(self) -> None:
        items = [{"question": "Some question?"}]
        with pytest.raises(KeyError, match="response"):
            evaluate_batch(items)

    def test_missing_question_in_second_item(self) -> None:
        items = [
            {"question": "Q1?", "response": "A1."},
            {"response": "A2."},
        ]
        with pytest.raises(KeyError, match="question"):
            evaluate_batch(items)

    def test_missing_response_in_second_item(self) -> None:
        items = [
            {"question": "Q1?", "response": "A1."},
            {"question": "Q2?"},
        ]
        with pytest.raises(KeyError, match="response"):
            evaluate_batch(items)
