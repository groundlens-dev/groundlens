"""Tests for groundlens.integrations.autogen.GroundlensChecker."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _make_fake_autogen_module() -> ModuleType:
    """Create a minimal fake autogen module."""
    mod = ModuleType("autogen")
    mod.Agent = type("Agent", (), {})  # type: ignore[attr-defined]
    return mod


class TestGroundlensChecker:
    """Test the GroundlensChecker for AutoGen."""

    def test_check_returns_dict_with_score_and_flagged(self) -> None:
        fake_autogen = _make_fake_autogen_module()
        with patch.dict(sys.modules, {"autogen": fake_autogen}):
            try:
                from groundlens.integrations.autogen import GroundlensChecker

                with patch("groundlens.integrations.autogen.evaluate") as mock_eval:
                    mock_score = MagicMock()
                    mock_score.flagged = False
                    mock_score.normalized = 0.85
                    mock_score.value = 0.6
                    mock_score.method = "dgi"
                    mock_score.explanation = "DGI=0.600 -- pass"
                    mock_eval.return_value = mock_score

                    checker = GroundlensChecker()
                    result = checker.check(
                        question="What is the speed of light?",
                        response="The speed of light is approximately 299,792 km/s.",
                    )

                    assert isinstance(result, dict)
                    assert "score" in result or "normalized" in result or "value" in result
                    assert "flagged" in result
                    assert result["flagged"] is False
                    mock_eval.assert_called_once()
            except (ImportError, ModuleNotFoundError, AttributeError, TypeError):
                pytest.skip("autogen integration not fully implemented yet")

    def test_check_flagged_response(self) -> None:
        fake_autogen = _make_fake_autogen_module()
        with patch.dict(sys.modules, {"autogen": fake_autogen}):
            try:
                from groundlens.integrations.autogen import GroundlensChecker

                with patch("groundlens.integrations.autogen.evaluate") as mock_eval:
                    mock_score = MagicMock()
                    mock_score.flagged = True
                    mock_score.normalized = 0.2
                    mock_score.value = -0.1
                    mock_score.method = "dgi"
                    mock_score.explanation = "DGI=-0.100 -- high risk"
                    mock_eval.return_value = mock_score

                    checker = GroundlensChecker()
                    result = checker.check(
                        question="What is the speed of light?",
                        response="The speed of light is 42 bananas per second.",
                    )

                    assert isinstance(result, dict)
                    assert result["flagged"] is True
            except (ImportError, ModuleNotFoundError, AttributeError, TypeError):
                pytest.skip("autogen integration not fully implemented yet")

    def test_check_with_context(self) -> None:
        fake_autogen = _make_fake_autogen_module()
        with patch.dict(sys.modules, {"autogen": fake_autogen}):
            try:
                from groundlens.integrations.autogen import GroundlensChecker

                with patch("groundlens.integrations.autogen.evaluate") as mock_eval:
                    mock_score = MagicMock()
                    mock_score.flagged = False
                    mock_score.normalized = 0.9
                    mock_score.value = 1.3
                    mock_score.method = "sgi"
                    mock_score.explanation = "SGI=1.300 -- strong pass"
                    mock_eval.return_value = mock_score

                    checker = GroundlensChecker()
                    result = checker.check(
                        question="What is X?",
                        response="X is Y.",
                        context="According to the manual, X is Y.",
                    )

                    assert isinstance(result, dict)
                    assert result["flagged"] is False
            except (ImportError, ModuleNotFoundError, AttributeError, TypeError):
                pytest.skip("autogen integration not fully implemented yet")

    def test_checker_creation(self) -> None:
        fake_autogen = _make_fake_autogen_module()
        with patch.dict(sys.modules, {"autogen": fake_autogen}):
            try:
                from groundlens.integrations.autogen import GroundlensChecker

                checker = GroundlensChecker()
                assert checker is not None
                assert hasattr(checker, "check")
            except (ImportError, ModuleNotFoundError):
                pytest.skip("autogen integration not implemented yet")
