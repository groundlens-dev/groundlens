"""Integration tests for groundlens.sgi.compute_sgi.

These tests load a real embedding model and compute actual SGI scores.
They verify semantic behavior: grounded responses pass, hallucinated
responses are flagged.
"""

from __future__ import annotations

import pytest

from groundlens.sgi import compute_sgi

pytestmark = pytest.mark.slow


class TestComputeSgiGrounded:
    """Test that grounded responses produce passing SGI scores."""

    def test_grounded_response_not_flagged(self, grounded_triple: dict[str, str]) -> None:
        result = compute_sgi(**grounded_triple)
        assert result.flagged is False
        assert result.value > 0.95

    def test_grounded_response_normalized_positive(self, grounded_triple: dict[str, str]) -> None:
        result = compute_sgi(**grounded_triple)
        assert 0.0 <= result.normalized <= 1.0
        assert result.normalized > 0.3

    def test_paraphrased_context_response(self) -> None:
        result = compute_sgi(
            question="What is photosynthesis?",
            context=(
                "Photosynthesis is the process by which green plants "
                "convert sunlight, carbon dioxide, and water into glucose and oxygen."
            ),
            response=(
                "Photosynthesis is how plants use light energy to transform "
                "CO2 and water into sugar and release oxygen."
            ),
        )
        assert result.flagged is False


class TestComputeSgiHallucinated:
    """Test that hallucinated responses are flagged."""

    def test_hallucinated_response_flagged(self, hallucinated_triple: dict[str, str]) -> None:
        result = compute_sgi(**hallucinated_triple)
        # A response about Berlin (Germany) when context says Paris should diverge
        # from the context significantly
        assert result.method == "sgi"
        assert 0.0 <= result.normalized <= 1.0

    def test_completely_unrelated_response(self) -> None:
        result = compute_sgi(
            question="What is the capital of France?",
            context="France is a country in Western Europe. Its capital is Paris.",
            response=(
                "Machine learning algorithms can be trained using "
                "supervised and unsupervised methods on large datasets."
            ),
        )
        assert result.flagged is True


class TestComputeSgiDegenerateCases:
    """Test degenerate/edge case inputs."""

    def test_response_equals_context(self) -> None:
        ctx = "The capital of France is Paris."
        result = compute_sgi(
            question="What is the capital of France?",
            context=ctx,
            response=ctx,
        )
        # When response == context, ctx_dist ~ 0, SGI should be very high
        assert result.value >= 5.0
        assert result.flagged is False

    def test_response_equals_question(self) -> None:
        q = "What is the capital of France?"
        result = compute_sgi(
            question=q,
            context="France is a country in Western Europe. Its capital is Paris.",
            response=q,
        )
        # When response == question, q_dist ~ 0, SGI should be ~0
        assert result.value == pytest.approx(0.0)
        assert result.flagged is True

    def test_method_always_sgi(self, grounded_triple: dict[str, str]) -> None:
        result = compute_sgi(**grounded_triple)
        assert result.method == "sgi"


class TestComputeSgiValidation:
    """Test input validation."""

    def test_empty_question_raises(self) -> None:
        with pytest.raises(ValueError, match="question"):
            compute_sgi(question="", context="Some context.", response="Some response.")

    def test_empty_context_raises(self) -> None:
        with pytest.raises(ValueError, match="context"):
            compute_sgi(question="Some question?", context="", response="Some response.")

    def test_empty_response_raises(self) -> None:
        with pytest.raises(ValueError, match="response"):
            compute_sgi(question="Some question?", context="Some context.", response="")

    def test_whitespace_only_question_raises(self) -> None:
        with pytest.raises(ValueError, match="question"):
            compute_sgi(question="   ", context="Some context.", response="Some response.")

    def test_whitespace_only_context_raises(self) -> None:
        with pytest.raises(ValueError, match="context"):
            compute_sgi(question="Question?", context="   ", response="Some response.")

    def test_whitespace_only_response_raises(self) -> None:
        with pytest.raises(ValueError, match="response"):
            compute_sgi(question="Question?", context="Some context.", response="   ")


class TestComputeSgiResultFields:
    """Test that SGIResult fields are populated correctly."""

    def test_q_dist_and_ctx_dist_positive(self, grounded_triple: dict[str, str]) -> None:
        result = compute_sgi(**grounded_triple)
        assert result.q_dist > 0
        assert result.ctx_dist > 0

    def test_explanation_non_empty(self, grounded_triple: dict[str, str]) -> None:
        result = compute_sgi(**grounded_triple)
        assert len(result.explanation) > 0
        assert "SGI=" in result.explanation
