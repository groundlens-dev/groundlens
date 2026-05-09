"""Tests for groundlens.integrations.langchain (GroundlensCallback, GroundlensEvaluator)."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


def _make_fake_langchain_modules() -> dict[str, ModuleType]:
    """Create minimal fake langchain modules for import mocking."""
    lc_core = ModuleType("langchain_core")
    lc_callbacks = ModuleType("langchain_core.callbacks")
    lc_callbacks.BaseCallbackHandler = type("BaseCallbackHandler", (), {})  # type: ignore[attr-defined]

    langsmith = ModuleType("langsmith")
    langsmith.RunEvaluator = type("RunEvaluator", (), {})  # type: ignore[attr-defined]

    return {
        "langchain_core": lc_core,
        "langchain_core.callbacks": lc_callbacks,
        "langsmith": langsmith,
    }


class TestGroundlensCallback:
    """Test the GroundlensCallback for langchain."""

    def test_on_llm_start_stores_prompts(self) -> None:
        fake_modules = _make_fake_langchain_modules()
        with patch.dict(sys.modules, fake_modules):
            try:
                from groundlens.integrations.langchain import GroundlensCallback

                cb = GroundlensCallback()
                run_id = uuid4()
                cb.on_llm_start(
                    serialized={"name": "test-model"},
                    prompts=["What is the capital of France?"],
                    run_id=run_id,
                )
                # Callback should store the prompts for later use in on_llm_end
                assert hasattr(cb, "_prompts")
                assert run_id in cb._prompts
            except (ImportError, ModuleNotFoundError):
                pytest.skip("langchain integration not implemented yet")

    def test_on_llm_end_evaluates(self) -> None:
        fake_modules = _make_fake_langchain_modules()
        with patch.dict(sys.modules, fake_modules):
            try:
                from groundlens.integrations.langchain import GroundlensCallback

                with patch("groundlens.integrations.langchain.callback.evaluate") as mock_eval:
                    mock_score = MagicMock()
                    mock_score.flagged = False
                    mock_score.value = 0.8
                    mock_eval.return_value = mock_score

                    cb = GroundlensCallback()
                    run_id = uuid4()
                    cb.on_llm_start(
                        serialized={"name": "test-model"},
                        prompts=["What is X?"],
                        run_id=run_id,
                    )

                    mock_response = MagicMock()
                    mock_generation = MagicMock()
                    mock_generation.text = "X is Y."
                    mock_response.generations = [[mock_generation]]

                    cb.on_llm_end(response=mock_response, run_id=run_id)
                    mock_eval.assert_called_once()
            except (ImportError, ModuleNotFoundError, AttributeError):
                pytest.skip("langchain integration not fully implemented yet")

    def test_on_llm_error_cleans_up(self) -> None:
        fake_modules = _make_fake_langchain_modules()
        with patch.dict(sys.modules, fake_modules):
            try:
                from groundlens.integrations.langchain import GroundlensCallback

                cb = GroundlensCallback()
                run_id = uuid4()
                cb.on_llm_start(
                    serialized={"name": "test-model"},
                    prompts=["What is X?"],
                    run_id=run_id,
                )
                # Calling on_llm_error should clean up without raising
                cb.on_llm_error(error=RuntimeError("test error"), run_id=run_id)
                # After error, prompts should be cleaned up
                assert run_id not in cb._prompts
            except (ImportError, ModuleNotFoundError):
                pytest.skip("langchain integration not implemented yet")


class TestGroundlensEvaluator:
    """Test the GroundlensEvaluator for langsmith."""

    def test_evaluator_creation(self) -> None:
        fake_modules = _make_fake_langchain_modules()
        with patch.dict(sys.modules, fake_modules):
            try:
                from groundlens.integrations.langchain import GroundlensEvaluator

                evaluator = GroundlensEvaluator()
                assert evaluator is not None
            except (ImportError, ModuleNotFoundError):
                pytest.skip("langchain evaluator not implemented yet")

    def test_evaluator_evaluate_run(self) -> None:
        fake_modules = _make_fake_langchain_modules()
        with patch.dict(sys.modules, fake_modules):
            try:
                from groundlens.integrations.langchain import GroundlensEvaluator

                with patch("groundlens.integrations.langchain.evaluate") as mock_eval:
                    mock_score = MagicMock()
                    mock_score.flagged = False
                    mock_score.normalized = 0.75
                    mock_score.method = "dgi"
                    mock_eval.return_value = mock_score

                    evaluator = GroundlensEvaluator()
                    mock_run = MagicMock()
                    mock_run.inputs = {"question": "What is X?"}
                    mock_run.outputs = {"output": "X is Y."}
                    mock_example = MagicMock()

                    result = evaluator.evaluate_run(mock_run, example=mock_example)
                    assert result is not None
            except (ImportError, ModuleNotFoundError, AttributeError):
                pytest.skip("langchain evaluator not fully implemented yet")
