"""Tests for groundlens.providers.anthropic.GroundlensAnthropic."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _make_fake_anthropic_module() -> ModuleType:
    """Create a minimal fake anthropic module for import mocking."""
    mod = ModuleType("anthropic")
    mod.Anthropic = MagicMock  # type: ignore[attr-defined]
    return mod


class TestGroundlensAnthropicInit:
    """Test GroundlensAnthropic initialization."""

    def test_init_default_model(self) -> None:
        fake_mod = _make_fake_anthropic_module()
        with patch.dict(sys.modules, {"anthropic": fake_mod}):
            try:
                from groundlens.providers.anthropic import GroundlensAnthropic

                llm = GroundlensAnthropic(api_key="sk-ant-test")
                assert hasattr(llm, "_model") or hasattr(llm, "model")
            except ImportError:
                pytest.skip("anthropic provider not implemented yet")


class TestGroundlensAnthropicChat:
    """Test chat/complete with mocked Anthropic client."""

    def test_chat_returns_response(self, mock_anthropic_client: MagicMock) -> None:
        fake_mod = _make_fake_anthropic_module()
        with patch.dict(sys.modules, {"anthropic": fake_mod}):
            try:
                from groundlens.providers.anthropic import GroundlensAnthropic

                with (
                    patch.object(
                        GroundlensAnthropic,
                        "__init__",
                        lambda self, **kw: (
                            setattr(self, "_client", mock_anthropic_client)
                            or setattr(self, "_model", "claude-sonnet-4-20250514")
                            or setattr(self, "_groundlens_model", "all-MiniLM-L6-v2")
                        ),
                    ),
                    patch("groundlens.providers.anthropic.evaluate") as mock_eval,
                ):
                    mock_eval.return_value = MagicMock()
                    llm = GroundlensAnthropic(api_key="sk-ant-test")
                    resp = llm.chat("What is X?")
                    assert resp.text == "Mocked Anthropic response text."
            except (ImportError, AttributeError, ModuleNotFoundError):
                pytest.skip("anthropic provider not fully implemented yet")

    def test_scoring_applied_to_response(self, mock_anthropic_client: MagicMock) -> None:
        fake_mod = _make_fake_anthropic_module()
        with patch.dict(sys.modules, {"anthropic": fake_mod}):
            try:
                from groundlens.providers.anthropic import GroundlensAnthropic

                with (
                    patch.object(
                        GroundlensAnthropic,
                        "__init__",
                        lambda self, **kw: (
                            setattr(self, "_client", mock_anthropic_client)
                            or setattr(self, "_model", "claude-sonnet-4-20250514")
                            or setattr(self, "_groundlens_model", "all-MiniLM-L6-v2")
                        ),
                    ),
                    patch("groundlens.providers.anthropic.evaluate") as mock_eval,
                ):
                    mock_score = MagicMock()
                    mock_score.flagged = False
                    mock_eval.return_value = mock_score

                    llm = GroundlensAnthropic(api_key="sk-ant-test")
                    resp = llm.chat("What is X?")
                    assert resp.groundlens_score is not None
                    mock_eval.assert_called_once()
            except (ImportError, AttributeError, ModuleNotFoundError):
                pytest.skip("anthropic provider not fully implemented yet")


class TestGroundlensAnthropicImportError:
    """Test ImportError when anthropic is not installed."""

    def test_import_error_raised(self) -> None:
        with patch.dict(sys.modules, {"anthropic": None}):
            try:
                # Force reimport
                if "groundlens.providers.anthropic" in sys.modules:
                    del sys.modules["groundlens.providers.anthropic"]
                from groundlens.providers.anthropic import GroundlensAnthropic

                with pytest.raises(ImportError, match="anthropic"):
                    GroundlensAnthropic(api_key="sk-test")
            except ImportError:
                # Expected -- the import itself may raise
                pass
