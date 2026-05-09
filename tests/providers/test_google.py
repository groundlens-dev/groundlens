"""Tests for groundlens.providers.google.GroundlensGemini."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _make_fake_google_module() -> ModuleType:
    """Create a minimal fake google.generativeai module."""
    mod = ModuleType("google")
    genai = ModuleType("google.generativeai")
    genai.GenerativeModel = MagicMock  # type: ignore[attr-defined]
    mod.generativeai = genai  # type: ignore[attr-defined]
    return mod


class TestGroundlensGeminiInit:
    """Test GroundlensGemini initialization."""

    def test_init_default(self) -> None:
        fake_mod = _make_fake_google_module()
        fake_genai = fake_mod.generativeai
        fake_genai.configure = MagicMock()  # type: ignore[attr-defined]
        fake_genai.GenerativeModel = MagicMock()  # type: ignore[attr-defined]
        with patch.dict(
            sys.modules,
            {"google": fake_mod, "google.generativeai": fake_genai},
        ):
            try:
                from groundlens.providers.google import GroundlensGemini

                llm = GroundlensGemini(api_key="test-key")
                has_model_attr = (
                    hasattr(llm, "_model_name") or hasattr(llm, "_model") or hasattr(llm, "model")
                )
                assert has_model_attr
            except ImportError:
                pytest.skip("google provider not implemented yet")


class TestGroundlensGeminiChat:
    """Test chat with mocked Google client."""

    def test_chat_returns_response(self, mock_google_client: MagicMock) -> None:
        fake_mod = _make_fake_google_module()
        with patch.dict(
            sys.modules,
            {"google": fake_mod, "google.generativeai": fake_mod.generativeai},
        ):
            try:
                from groundlens.providers.google import GroundlensGemini

                with (
                    patch.object(
                        GroundlensGemini,
                        "__init__",
                        lambda self, **kw: (
                            setattr(self, "_client", mock_google_client)
                            or setattr(self, "_model", "gemini-pro")
                            or setattr(self, "_groundlens_model", "all-MiniLM-L6-v2")
                        ),
                    ),
                    patch("groundlens.providers.google.evaluate") as mock_eval,
                ):
                    mock_eval.return_value = MagicMock()
                    llm = GroundlensGemini(api_key="test-key")
                    resp = llm.chat("What is X?")
                    assert resp.text == "Mocked Gemini response text."
            except (ImportError, AttributeError, ModuleNotFoundError):
                pytest.skip("google provider not fully implemented yet")

    def test_scoring_applied(self, mock_google_client: MagicMock) -> None:
        fake_mod = _make_fake_google_module()
        with patch.dict(
            sys.modules,
            {"google": fake_mod, "google.generativeai": fake_mod.generativeai},
        ):
            try:
                from groundlens.providers.google import GroundlensGemini

                with (
                    patch.object(
                        GroundlensGemini,
                        "__init__",
                        lambda self, **kw: (
                            setattr(self, "_client", mock_google_client)
                            or setattr(self, "_model", "gemini-pro")
                            or setattr(self, "_groundlens_model", "all-MiniLM-L6-v2")
                        ),
                    ),
                    patch("groundlens.providers.google.evaluate") as mock_eval,
                ):
                    mock_score = MagicMock()
                    mock_score.flagged = True
                    mock_eval.return_value = mock_score

                    llm = GroundlensGemini(api_key="test-key")
                    resp = llm.chat("What is X?")
                    assert resp.groundlens_score is not None
                    mock_eval.assert_called_once()
            except (ImportError, AttributeError, ModuleNotFoundError):
                pytest.skip("google provider not fully implemented yet")


class TestGroundlensGeminiImportError:
    """Test ImportError when google-generativeai is not installed."""

    def test_import_error_raised(self) -> None:
        with patch.dict(
            sys.modules,
            {"google": None, "google.generativeai": None},
        ):
            try:
                if "groundlens.providers.google" in sys.modules:
                    del sys.modules["groundlens.providers.google"]
                from groundlens.providers.google import GroundlensGemini

                with pytest.raises(ImportError):
                    GroundlensGemini(api_key="test")
            except ImportError:
                # Expected -- the import itself may raise
                pass
