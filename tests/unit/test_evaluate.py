"""Unit tests for groundlens.evaluate — auto-select and batch API.

These tests mock compute_sgi / compute_dgi so no embedding model is loaded.

Note: ``groundlens.__init__`` re-exports ``evaluate`` as a function, which
shadows the module name when using ``@patch("groundlens.evaluate.X")``.
We import the module explicitly and use ``patch.object`` to avoid this.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

# groundlens.__init__ re-exports a function called ``evaluate``, which
# shadows the module ``groundlens.evaluate`` in the package namespace.
# We grab the actual module object from sys.modules so patch.object works.
import groundlens.evaluate  # noqa: F401

_eval_mod = sys.modules["groundlens.evaluate"]

from groundlens.evaluate import evaluate, evaluate_batch  # noqa: E402
from groundlens.score import DGIResult, SGIResult  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_SGI = SGIResult(value=1.25, normalized=0.62, flagged=False, q_dist=0.8, ctx_dist=0.64)
_MOCK_DGI = DGIResult(value=0.42, normalized=0.71, flagged=False)


def _fake_sgi(**kwargs):
    return _MOCK_SGI


def _fake_dgi(**kwargs):
    return _MOCK_DGI


# ---------------------------------------------------------------------------
# evaluate() routing tests
# ---------------------------------------------------------------------------


class TestEvaluateRouting:
    """Verify evaluate() picks SGI when context is given, DGI otherwise."""

    @patch.object(_eval_mod, "compute_sgi", side_effect=_fake_sgi)
    def test_context_routes_to_sgi(self, mock_sgi) -> None:
        score = evaluate(question="Q?", response="A.", context="Source.")
        assert score.method == "sgi"
        mock_sgi.assert_called_once()

    @patch.object(_eval_mod, "compute_dgi", side_effect=_fake_dgi)
    def test_no_context_routes_to_dgi(self, mock_dgi) -> None:
        score = evaluate(question="Q?", response="A.")
        assert score.method == "dgi"
        mock_dgi.assert_called_once()

    @patch.object(_eval_mod, "compute_dgi", side_effect=_fake_dgi)
    def test_empty_context_routes_to_dgi(self, mock_dgi) -> None:
        score = evaluate(question="Q?", response="A.", context="")
        assert score.method == "dgi"

    @patch.object(_eval_mod, "compute_dgi", side_effect=_fake_dgi)
    def test_whitespace_context_routes_to_dgi(self, mock_dgi) -> None:
        score = evaluate(question="Q?", response="A.", context="   ")
        assert score.method == "dgi"

    @patch.object(_eval_mod, "compute_sgi", side_effect=_fake_sgi)
    def test_score_values_propagated(self, mock_sgi) -> None:
        score = evaluate(question="Q?", response="A.", context="Source.")
        assert score.value == _MOCK_SGI.value
        assert score.normalized == _MOCK_SGI.normalized
        assert score.flagged == _MOCK_SGI.flagged
        assert score.detail is _MOCK_SGI

    @patch.object(_eval_mod, "compute_dgi", side_effect=_fake_dgi)
    def test_reference_csv_passed_to_dgi(self, mock_dgi) -> None:
        evaluate(question="Q?", response="A.", reference_csv="cal.csv")
        _, kwargs = mock_dgi.call_args
        assert kwargs["reference_csv"] == "cal.csv"


# ---------------------------------------------------------------------------
# evaluate_batch() tests
# ---------------------------------------------------------------------------


class TestEvaluateBatch:
    """Verify batch evaluation handles valid and invalid inputs."""

    @patch.object(_eval_mod, "compute_sgi", side_effect=_fake_sgi)
    @patch.object(_eval_mod, "compute_dgi", side_effect=_fake_dgi)
    def test_batch_mixed_methods(self, mock_dgi, mock_sgi) -> None:
        items = [
            {"question": "Q1?", "response": "A1.", "context": "C1."},
            {"question": "Q2?", "response": "A2."},
        ]
        results = evaluate_batch(items)
        assert len(results) == 2
        assert results[0].method == "sgi"
        assert results[1].method == "dgi"

    def test_missing_question_raises_key_error(self) -> None:
        items = [{"response": "A."}]
        with pytest.raises(KeyError, match="question"):
            evaluate_batch(items)

    def test_missing_response_raises_key_error(self) -> None:
        items = [{"question": "Q?"}]
        with pytest.raises(KeyError, match="response"):
            evaluate_batch(items)

    @patch.object(_eval_mod, "compute_dgi", side_effect=_fake_dgi)
    def test_empty_batch_returns_empty(self, mock_dgi) -> None:
        results = evaluate_batch([])
        assert results == []
