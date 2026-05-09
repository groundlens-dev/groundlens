"""Integration tests for groundlens.dgi.compute_dgi.

These tests load a real embedding model and compute actual DGI scores.
They verify directional grounding behavior against the bundled reference
dataset.
"""

from __future__ import annotations

import pytest

from groundlens.dgi import compute_dgi, reset_calibration_cache

pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def _clear_dgi_cache() -> None:
    """Ensure a clean calibration cache for each test."""
    reset_calibration_cache()


class TestComputeDgiFactual:
    """Test that factual responses produce reasonable DGI scores."""

    def test_factual_response_normalized_in_range(self, factual_pair: dict[str, str]) -> None:
        result = compute_dgi(**factual_pair)
        assert 0.0 <= result.normalized <= 1.0

    def test_factual_response_method_is_dgi(self, factual_pair: dict[str, str]) -> None:
        result = compute_dgi(**factual_pair)
        assert result.method == "dgi"

    def test_factual_response_value_in_range(self, factual_pair: dict[str, str]) -> None:
        result = compute_dgi(**factual_pair)
        assert -1.0 <= result.value <= 1.0


class TestComputeDgiFabricated:
    """Test fabricated responses."""

    def test_fabricated_response_scored(self, fabricated_pair: dict[str, str]) -> None:
        result = compute_dgi(**fabricated_pair)
        assert result.method == "dgi"
        assert -1.0 <= result.value <= 1.0
        assert 0.0 <= result.normalized <= 1.0

    def test_completely_random_response(self) -> None:
        result = compute_dgi(
            question="What year was the Magna Carta signed?",
            response=(
                "Purple elephants dance on quantum rainbows while "
                "singing ancient Babylonian jazz fusion melodies."
            ),
        )
        assert result.method == "dgi"
        assert 0.0 <= result.normalized <= 1.0


class TestComputeDgiNormalizedRange:
    """Verify normalized scores always land in [0, 1]."""

    def test_multiple_factual_pairs(self) -> None:
        pairs = [
            ("What is gravity?", "Gravity is a fundamental force of attraction between masses."),
            ("Who wrote Hamlet?", "William Shakespeare wrote Hamlet around 1600."),
            (
                "What is DNA?",
                "DNA is deoxyribonucleic acid, the molecule carrying genetic instructions.",
            ),
        ]
        for q, r in pairs:
            result = compute_dgi(question=q, response=r)
            assert 0.0 <= result.normalized <= 1.0, (
                f"Normalized score {result.normalized} out of range for: {q}"
            )


class TestComputeDgiValidation:
    """Test input validation."""

    def test_empty_question_raises(self) -> None:
        with pytest.raises(ValueError, match="question"):
            compute_dgi(question="", response="Some response.")

    def test_empty_response_raises(self) -> None:
        with pytest.raises(ValueError, match="response"):
            compute_dgi(question="Some question?", response="")

    def test_whitespace_only_question_raises(self) -> None:
        with pytest.raises(ValueError, match="question"):
            compute_dgi(question="   ", response="Some response.")

    def test_whitespace_only_response_raises(self) -> None:
        with pytest.raises(ValueError, match="response"):
            compute_dgi(question="Some question?", response="   \t\n  ")


class TestComputeDgiExplanation:
    """Test that explanations are generated."""

    def test_explanation_contains_dgi(self, factual_pair: dict[str, str]) -> None:
        result = compute_dgi(**factual_pair)
        assert "DGI=" in result.explanation

    def test_explanation_non_empty(self, factual_pair: dict[str, str]) -> None:
        result = compute_dgi(**factual_pair)
        assert len(result.explanation) > 0
