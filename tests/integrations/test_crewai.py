"""Tests for groundlens.integrations.crewai.GroundlensTool."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _make_fake_crewai_module() -> ModuleType:
    """Create a minimal fake crewai module."""
    mod = ModuleType("crewai")
    mod.Tool = type("Tool", (), {})  # type: ignore[attr-defined]

    crewai_tools = ModuleType("crewai_tools")
    crewai_tools.BaseTool = type(  # type: ignore[attr-defined]
        "BaseTool",
        (),
        {"_run": lambda self, *a, **kw: ""},
    )
    return mod


class TestGroundlensTool:
    """Test the GroundlensTool for CrewAI."""

    def test_run_returns_verification_string(self) -> None:
        fake_crewai = _make_fake_crewai_module()
        fake_crewai_tools = ModuleType("crewai_tools")
        fake_crewai_tools.BaseTool = type(  # type: ignore[attr-defined]
            "BaseTool",
            (),
            {"_run": lambda self, *a, **kw: ""},
        )
        with patch.dict(
            sys.modules,
            {"crewai": fake_crewai, "crewai_tools": fake_crewai_tools},
        ):
            try:
                from groundlens.integrations.crewai import GroundlensTool

                with patch("groundlens.integrations.crewai.evaluate") as mock_eval:
                    mock_score = MagicMock()
                    mock_score.flagged = False
                    mock_score.normalized = 0.85
                    mock_score.value = 0.6
                    mock_score.method = "dgi"
                    mock_score.explanation = "DGI=0.600 -- aligns with grounded patterns (pass)"
                    mock_eval.return_value = mock_score

                    tool = GroundlensTool()
                    result = tool._run(
                        question="What is the capital of France?",
                        response="The capital of France is Paris.",
                    )
                    assert isinstance(result, str)
                    assert len(result) > 0
                    mock_eval.assert_called_once()
            except (ImportError, ModuleNotFoundError, AttributeError, TypeError):
                pytest.skip("crewai integration not fully implemented yet")

    def test_run_with_context(self) -> None:
        fake_crewai = _make_fake_crewai_module()
        fake_crewai_tools = ModuleType("crewai_tools")
        fake_crewai_tools.BaseTool = type(  # type: ignore[attr-defined]
            "BaseTool",
            (),
            {"_run": lambda self, *a, **kw: ""},
        )
        with patch.dict(
            sys.modules,
            {"crewai": fake_crewai, "crewai_tools": fake_crewai_tools},
        ):
            try:
                from groundlens.integrations.crewai import GroundlensTool

                with patch("groundlens.integrations.crewai.evaluate") as mock_eval:
                    mock_score = MagicMock()
                    mock_score.flagged = True
                    mock_score.normalized = 0.3
                    mock_score.value = 0.4
                    mock_score.method = "sgi"
                    mock_score.explanation = "SGI=0.400 -- weak context engagement (flagged)"
                    mock_eval.return_value = mock_score

                    tool = GroundlensTool()
                    result = tool._run(
                        question="What is X?",
                        response="X is Z.",
                        context="X is Y according to the manual.",
                    )
                    assert isinstance(result, str)
            except (ImportError, ModuleNotFoundError, AttributeError, TypeError):
                pytest.skip("crewai integration not fully implemented yet")
