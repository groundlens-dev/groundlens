"""Tests for groundlens.providers.openai.GroundlensOpenAI."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

import groundlens.providers.openai as openai_mod


class TestGroundlensOpenAIInit:
    """Test GroundlensOpenAI initialization."""

    def test_init_creates_client(self, mock_openai_client: MagicMock) -> None:
        with patch.object(
            openai_mod,
            "_get_openai_client",
            return_value=mock_openai_client,
        ):
            llm = openai_mod.GroundlensOpenAI(api_key="sk-test-key")
            assert llm._model == "gpt-4o"
            assert llm._groundlens_model == "all-MiniLM-L6-v2"

    def test_init_custom_model(self, mock_openai_client: MagicMock) -> None:
        with patch.object(
            openai_mod,
            "_get_openai_client",
            return_value=mock_openai_client,
        ):
            llm = openai_mod.GroundlensOpenAI(
                api_key="sk-test-key",
                model="gpt-4o-mini",
                groundlens_model="all-mpnet-base-v2",
            )
            assert llm._model == "gpt-4o-mini"
            assert llm._groundlens_model == "all-mpnet-base-v2"


class TestGroundlensOpenAIChat:
    """Test the chat method with mocked OpenAI and groundlens scoring."""

    def test_chat_returns_llm_response(self, mock_openai_client: MagicMock) -> None:
        with (
            patch.object(openai_mod, "_get_openai_client", return_value=mock_openai_client),
            patch.object(openai_mod, "evaluate") as mock_evaluate,
        ):
            mock_score = MagicMock()
            mock_score.method = "dgi"
            mock_score.value = 0.5
            mock_score.flagged = False
            mock_evaluate.return_value = mock_score

            llm = openai_mod.GroundlensOpenAI(api_key="sk-test-key")
            resp = llm.chat("What is the meaning of life?")

            assert resp.text == "Mocked LLM response text."
            assert resp.model == "gpt-4o"
            assert resp.groundlens_score is not None

    def test_chat_calls_openai_api(self, mock_openai_client: MagicMock) -> None:
        with (
            patch.object(openai_mod, "_get_openai_client", return_value=mock_openai_client),
            patch.object(openai_mod, "evaluate") as mock_evaluate,
        ):
            mock_evaluate.return_value = MagicMock()

            llm = openai_mod.GroundlensOpenAI(api_key="sk-test-key")
            llm.chat("Hello world")

            mock_openai_client.chat.completions.create.assert_called_once()

    def test_chat_with_context_passes_to_evaluate(self, mock_openai_client: MagicMock) -> None:
        with (
            patch.object(openai_mod, "_get_openai_client", return_value=mock_openai_client),
            patch.object(openai_mod, "evaluate") as mock_evaluate,
        ):
            mock_evaluate.return_value = MagicMock()

            llm = openai_mod.GroundlensOpenAI(api_key="sk-test-key")
            llm.chat("Summarize this.", context="The source document text.")

            mock_evaluate.assert_called_once()
            call_kwargs = mock_evaluate.call_args
            assert "The source document text." in str(call_kwargs)

    def test_chat_usage_metadata(self, mock_openai_client: MagicMock) -> None:
        with (
            patch.object(openai_mod, "_get_openai_client", return_value=mock_openai_client),
            patch.object(openai_mod, "evaluate") as mock_evaluate,
        ):
            mock_evaluate.return_value = MagicMock()

            llm = openai_mod.GroundlensOpenAI(api_key="sk-test-key")
            resp = llm.chat("Hello")

            assert resp.usage["prompt_tokens"] == 10
            assert resp.usage["completion_tokens"] == 20
            assert resp.usage["total_tokens"] == 30

    def test_complete_delegates_to_chat(self, mock_openai_client: MagicMock) -> None:
        with (
            patch.object(openai_mod, "_get_openai_client", return_value=mock_openai_client),
            patch.object(openai_mod, "evaluate") as mock_evaluate,
        ):
            mock_evaluate.return_value = MagicMock()

            llm = openai_mod.GroundlensOpenAI(api_key="sk-test-key")
            resp = llm.complete("Test prompt", context="Test context")

            assert resp.text == "Mocked LLM response text."


class TestGroundlensOpenAIImportError:
    """Test ImportError when openai is not installed."""

    def test_import_error_message(self) -> None:
        with patch.dict(sys.modules, {"openai": None}), pytest.raises(ImportError, match="openai"):
            openai_mod._get_openai_client("sk-test")
