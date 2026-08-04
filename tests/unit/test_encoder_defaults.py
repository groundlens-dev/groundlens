"""Every public entry point must default to the encoder the thresholds were fit on.

The 2026.7.23 release made ``sentence-transformers/sentence-t5-large`` the
default and said plainly that the bundled thresholds and the DGI ``mu_hat``
are only meaningful with it. The change reached ``sgi.py``, ``dgi.py`` and
``evaluate.py``. It did not reach the CLI, the three provider wrappers or the
six framework integrations, all of which kept scoring with the retired 384-dim
``all-MiniLM-L6-v2`` against 768-dim-calibrated cut-points.

There was even a unit test asserting the old CLI default, so the defect was
locked in rather than caught. These tests replace it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from groundlens._internal.embeddings import DEFAULT_MODEL
from groundlens.cli.main import _build_parser

WRAPPER_MODULES = [
    "groundlens.providers.openai",
    "groundlens.providers.anthropic",
    "groundlens.providers.google",
    "groundlens.integrations.crewai.tool",
    "groundlens.integrations.langgraph.callback",
    "groundlens.integrations.semantic_kernel.filter",
    "groundlens.integrations.autogen.checker",
    "groundlens.integrations.langchain.evaluator",
    "groundlens.integrations.langchain.callback",
]


@pytest.mark.parametrize("verb", ["check", "evaluate", "calibrate", "doctor", "benchmark"])
def test_cli_model_default_is_the_calibrated_encoder(verb: str) -> None:
    parser = _build_parser()
    subparsers = parser._subparsers._group_actions[0]
    action = next(a for a in subparsers.choices[verb]._actions if a.dest == "model")
    assert action.default == DEFAULT_MODEL


@pytest.mark.parametrize("module_path", WRAPPER_MODULES)
def test_no_wrapper_hardcodes_the_retired_encoder(module_path: str) -> None:
    spec = importlib.util.find_spec(module_path)
    assert spec is not None
    assert spec.origin is not None
    source = Path(spec.origin).read_text(encoding="utf-8")
    assert 'groundlens_model: str = "all-MiniLM-L6-v2"' not in source


@pytest.mark.parametrize("module_path", WRAPPER_MODULES)
def test_every_wrapper_defaults_to_default_model(module_path: str) -> None:
    spec = importlib.util.find_spec(module_path)
    assert spec is not None
    assert spec.origin is not None
    source = Path(spec.origin).read_text(encoding="utf-8")
    assert "groundlens_model: str = DEFAULT_MODEL" in source
