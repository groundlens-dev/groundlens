"""Shared fixtures for the groundlens test suite."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

if TYPE_CHECKING:
    from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Embedding model fixture (session-scoped, loads once)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def embedding_model():
    """Load the default sentence-transformer model once for the session.

    Tests marked ``@pytest.mark.slow`` may use this to compute real
    embeddings.  Unit tests should prefer the ``mock_encode_texts``
    fixture instead.
    """
    from groundlens._internal.embeddings import get_encoder

    return get_encoder()


# ---------------------------------------------------------------------------
# Mock fixtures for API / embedding calls
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_encode_texts():
    """Patch ``encode_texts`` to return deterministic fake embeddings.

    The mock returns random-but-reproducible vectors so geometry tests
    that sit above the embedding layer can run without downloading a
    real model.
    """
    rng = np.random.default_rng(42)

    def _fake_encode(texts: list[str], model_name: str = "mock") -> NDArray[np.float32]:
        return rng.standard_normal((len(texts), 384)).astype(np.float32)

    with patch("groundlens._internal.embeddings.encode_texts", side_effect=_fake_encode) as m:
        yield m


@pytest.fixture
def mock_openai_client():
    """Return a mock that mimics ``openai.OpenAI().chat.completions.create``."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Mocked LLM response text."
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage.prompt_tokens = 10
    mock_completion.usage.completion_tokens = 20
    mock_completion.usage.total_tokens = 30
    mock_client.chat.completions.create.return_value = mock_completion
    return mock_client


@pytest.fixture
def mock_anthropic_client():
    """Return a mock that mimics the Anthropic messages API."""
    mock_client = MagicMock()
    mock_block = MagicMock()
    mock_block.text = "Mocked Anthropic response text."
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 20
    mock_client.messages.create.return_value = mock_response
    return mock_client


@pytest.fixture
def mock_google_client():
    """Return a mock that mimics the Google Generative AI client."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Mocked Gemini response text."
    mock_client.generate_content.return_value = mock_response
    return mock_client


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def grounded_triple() -> dict[str, str]:
    """A question-context-response triple where the response is grounded."""
    return {
        "question": "What is the capital of France?",
        "context": (
            "France is a country in Western Europe. Its capital and largest city is Paris."
        ),
        "response": "The capital of France is Paris.",
    }


@pytest.fixture
def hallucinated_triple() -> dict[str, str]:
    """A question-context-response triple where the response is fabricated."""
    return {
        "question": "What is the capital of France?",
        "context": (
            "France is a country in Western Europe. Its capital and largest city is Paris."
        ),
        "response": (
            "The capital of France is Berlin, which is known for its "
            "beautiful architecture and rich history in Germany."
        ),
    }


@pytest.fixture
def factual_pair() -> dict[str, str]:
    """A question-response pair where the answer is factually correct."""
    return {
        "question": "What causes the seasons on Earth?",
        "response": (
            "Seasons on Earth are primarily caused by the 23.5-degree "
            "axial tilt of Earth's rotational axis relative to its orbital plane."
        ),
    }


@pytest.fixture
def fabricated_pair() -> dict[str, str]:
    """A question-response pair where the answer is fabricated."""
    return {
        "question": "What causes the seasons on Earth?",
        "response": (
            "Seasons are caused by the Sun moving closer and farther from "
            "Earth in an elliptical orbit, creating temperature changes."
        ),
    }


# ---------------------------------------------------------------------------
# pytest markers
# ---------------------------------------------------------------------------


def pytest_configure(config: Any) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests that load real embedding models")
