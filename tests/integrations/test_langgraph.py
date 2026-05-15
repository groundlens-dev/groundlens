"""Tests for groundlens.integrations.langgraph (callback, trace, report)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from groundlens.integrations.langgraph.trace import (
    AgentStep,
    AgentTrace,
    _triage_label,
)
from groundlens.score import GroundlensScore

if TYPE_CHECKING:
    from pathlib import Path


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_score(
    *,
    value: float = 0.85,
    normalized: float = 0.70,
    flagged: bool = False,
    method: str = "sgi",
    explanation: str = "SGI=0.850 — partial engagement (review recommended)",
) -> GroundlensScore:
    """Create a GroundlensScore for testing."""
    detail = MagicMock()
    detail.value = value
    detail.normalized = normalized
    detail.flagged = flagged
    detail.method = method
    detail.explanation = explanation
    return GroundlensScore(
        value=value,
        normalized=normalized,
        flagged=flagged,
        method=method,
        explanation=explanation,
        detail=detail,
    )


def _make_step(
    *,
    node_name: str = "retriever",
    step_index: int = 0,
    triage: str = "trusted",
    method: str = "sgi",
    value: float = 1.25,
    normalized: float = 0.80,
    flagged: bool = False,
    duration_ms: float = 42.0,
    context: str | None = "Source document text.",
) -> AgentStep:
    """Create an AgentStep for testing."""
    score = _make_score(
        value=value,
        normalized=normalized,
        flagged=flagged,
        method=method,
        explanation=f"{method.upper()}={value:.3f}",
    )
    return AgentStep(
        node_name=node_name,
        step_index=step_index,
        input_text="What is X?",
        output_text="X is Y.",
        context=context,
        score=score,
        triage=triage,
        method=method,
        duration_ms=duration_ms,
    )


# ── _triage_label ────────────────────────────────────────────────────────────


class TestTriageLabel:
    """Test _triage_label classification logic."""

    def test_flagged_score_returns_flagged(self) -> None:
        score = _make_score(flagged=True, normalized=0.3)
        assert _triage_label(score) == "flagged"

    def test_low_normalized_returns_review(self) -> None:
        score = _make_score(flagged=False, normalized=0.5)
        assert _triage_label(score) == "review"

    def test_high_normalized_returns_trusted(self) -> None:
        score = _make_score(flagged=False, normalized=0.8)
        assert _triage_label(score) == "trusted"

    def test_boundary_at_0_6_returns_trusted(self) -> None:
        score = _make_score(flagged=False, normalized=0.6)
        assert _triage_label(score) == "trusted"

    def test_just_below_0_6_returns_review(self) -> None:
        score = _make_score(flagged=False, normalized=0.59)
        assert _triage_label(score) == "review"

    def test_flagged_overrides_high_normalized(self) -> None:
        """Flagged takes precedence even if normalized is high."""
        score = _make_score(flagged=True, normalized=0.95)
        assert _triage_label(score) == "flagged"


# ── AgentStep ────────────────────────────────────────────────────────────────


class TestAgentStep:
    """Test AgentStep data class and serialization."""

    def test_to_dict_includes_all_fields(self) -> None:
        step = _make_step()
        d = step.to_dict()
        assert d["node_name"] == "retriever"
        assert d["step_index"] == 0
        assert d["input_text"] == "What is X?"
        assert d["output_text"] == "X is Y."
        assert d["context"] == "Source document text."
        assert d["triage"] == "trusted"
        assert d["method"] == "sgi"
        assert d["duration_ms"] == 42.0

    def test_to_dict_score_is_expanded(self) -> None:
        step = _make_step(value=1.25, normalized=0.80, method="sgi")
        d = step.to_dict()
        assert "score" in d
        assert d["score"]["value"] == 1.25
        assert d["score"]["normalized"] == 0.80
        assert d["score"]["flagged"] is False
        assert d["score"]["method"] == "sgi"

    def test_to_dict_with_none_context(self) -> None:
        step = _make_step(context=None)
        d = step.to_dict()
        assert d["context"] is None

    def test_to_dict_is_json_serializable(self) -> None:
        step = _make_step()
        serialized = json.dumps(step.to_dict())
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["node_name"] == "retriever"


# ── AgentTrace ───────────────────────────────────────────────────────────────


class TestAgentTrace:
    """Test AgentTrace aggregation and export methods."""

    def test_empty_trace_properties(self) -> None:
        trace = AgentTrace()
        assert trace.total_steps == 0
        assert trace.flagged_steps == 0
        assert trace.review_steps == 0
        assert trace.trusted_steps == 0
        assert trace.total_duration_ms == 0.0

    def test_counts_by_triage(self) -> None:
        trace = AgentTrace(
            steps=[
                _make_step(triage="trusted", step_index=0),
                _make_step(triage="trusted", step_index=1),
                _make_step(triage="review", step_index=2),
                _make_step(
                    triage="flagged",
                    step_index=3,
                    flagged=True,
                ),
            ]
        )
        assert trace.total_steps == 4
        assert trace.trusted_steps == 2
        assert trace.review_steps == 1
        assert trace.flagged_steps == 1

    def test_total_duration_ms(self) -> None:
        trace = AgentTrace(
            steps=[
                _make_step(duration_ms=100.0, step_index=0),
                _make_step(duration_ms=200.0, step_index=1),
                _make_step(duration_ms=50.5, step_index=2),
            ]
        )
        assert trace.total_duration_ms == pytest.approx(350.5)

    def test_summary_with_flagged_steps(self) -> None:
        trace = AgentTrace(
            steps=[
                _make_step(
                    node_name="fact_check",
                    triage="flagged",
                    method="dgi",
                    value=0.18,
                    flagged=True,
                    step_index=0,
                    duration_ms=100.0,
                ),
                _make_step(
                    node_name="retriever",
                    triage="trusted",
                    step_index=1,
                    duration_ms=50.0,
                ),
            ]
        )
        summary = trace.summary()
        assert "2 steps" in summary
        assert "1 flagged" in summary
        assert "1 trusted" in summary
        assert "fact_check" in summary
        assert "DGI=0.180" in summary

    def test_summary_with_review_steps(self) -> None:
        trace = AgentTrace(
            steps=[
                _make_step(
                    node_name="analyzer",
                    triage="review",
                    method="sgi",
                    value=1.05,
                    step_index=0,
                ),
            ]
        )
        summary = trace.summary()
        assert "1 review" in summary
        assert "analyzer" in summary
        assert "SGI=1.050" in summary

    def test_summary_empty_trace(self) -> None:
        trace = AgentTrace()
        summary = trace.summary()
        assert "0 steps" in summary

    def test_to_dict_structure(self) -> None:
        trace = AgentTrace(steps=[_make_step(step_index=0), _make_step(step_index=1)])
        d = trace.to_dict()
        assert d["total_steps"] == 2
        assert d["flagged_steps"] == 0
        assert d["review_steps"] == 0
        assert d["trusted_steps"] == 2
        assert len(d["steps"]) == 2

    def test_to_json_is_valid(self) -> None:
        trace = AgentTrace(steps=[_make_step()])
        j = trace.to_json()
        parsed = json.loads(j)
        assert parsed["total_steps"] == 1
        assert len(parsed["steps"]) == 1

    def test_to_html_returns_string(self) -> None:
        trace = AgentTrace(steps=[_make_step()])
        html = trace.to_html()
        assert "<!DOCTYPE html>" in html
        assert "groundlens Triage Report" in html
        assert "retriever" in html

    def test_to_html_writes_file(self, tmp_path: Path) -> None:
        trace = AgentTrace(steps=[_make_step()])
        out = tmp_path / "report.html"
        html = trace.to_html(path=out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert content == html
        assert "groundlens" in content

    def test_to_html_empty_trace(self) -> None:
        trace = AgentTrace()
        html = trace.to_html()
        assert "0" in html  # 0 steps
        assert "<!DOCTYPE html>" in html


# ── HTML Report ──────────────────────────────────────────────────────────────


class TestHtmlReport:
    """Test report.py rendering details."""

    def test_triage_colors_in_html(self) -> None:
        trace = AgentTrace(
            steps=[
                _make_step(triage="trusted", step_index=0),
                _make_step(
                    triage="flagged",
                    flagged=True,
                    step_index=1,
                ),
                _make_step(triage="review", step_index=2),
            ]
        )
        html = trace.to_html()
        assert "#10b981" in html  # trusted green
        assert "#ef4444" in html  # flagged red
        assert "#f59e0b" in html  # review amber

    def test_method_badges_in_html(self) -> None:
        trace = AgentTrace(
            steps=[
                _make_step(method="sgi", step_index=0),
                _make_step(
                    method="dgi",
                    context=None,
                    step_index=1,
                ),
            ]
        )
        html = trace.to_html()
        assert "SGI" in html
        assert "DGI" in html
        assert "badge-sgi" in html
        assert "badge-dgi" in html

    def test_context_section_present_when_context_exists(self) -> None:
        trace = AgentTrace(steps=[_make_step(context="Some tool output.")])
        html = trace.to_html()
        assert "Context (tool output)" in html
        assert "Some tool output." in html

    def test_context_section_absent_when_no_context(self) -> None:
        trace = AgentTrace(steps=[_make_step(context=None)])
        html = trace.to_html()
        assert "Context (tool output)" not in html

    def test_html_escapes_special_characters(self) -> None:
        step = _make_step()
        # Override input_text with HTML-dangerous content
        object.__setattr__(step, "input_text", "<script>alert('xss')</script>")
        trace = AgentTrace(steps=[step])
        html = trace.to_html()
        # The injected script should be escaped in the detail-text section
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html
        # The actual report's own <script> for filtering is fine
        assert "filterSteps" in html

    def test_filter_buttons_present(self) -> None:
        trace = AgentTrace(steps=[_make_step()])
        html = trace.to_html()
        assert "filterSteps" in html
        assert "Flagged" in html
        assert "Review" in html
        assert "Trusted" in html


# ── GroundlensLangGraphCallback ──────────────────────────────────────────────


class TestGroundlensLangGraphCallback:
    """Test the callback handler's lifecycle hooks."""

    def test_init_defaults(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        assert cb._groundlens_model == "all-MiniLM-L6-v2"
        assert cb._context_key == "context"
        assert cb._current_node == "unknown"
        assert cb._step_counter == 0

    def test_on_chain_start_tracks_node(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        run_id = uuid4()
        cb.on_chain_start(
            serialized={"name": "some_chain"},
            inputs={},
            run_id=run_id,
            metadata={"langgraph_node": "retriever"},
        )
        assert cb._current_node == "retriever"

    def test_on_chain_start_falls_back_to_serialized_name(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        cb.on_chain_start(
            serialized={"name": "my_custom_node"},
            inputs={},
            run_id=uuid4(),
            metadata={},
        )
        assert cb._current_node == "my_custom_node"

    def test_on_chain_start_ignores_generic_names(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        cb.on_chain_start(
            serialized={"name": "RunnableSequence"},
            inputs={},
            run_id=uuid4(),
            metadata={},
        )
        assert cb._current_node == "unknown"

    def test_on_tool_start_and_end_captures_output(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        run_id = uuid4()
        cb.on_tool_start(
            serialized={"name": "search_tool"},
            input_str="query",
            run_id=run_id,
        )
        assert cb._last_tool_name == "search_tool"

        cb.on_tool_end(output="Search result text", run_id=run_id)
        assert cb._last_tool_output == "Search result text"

    def test_on_tool_end_ignores_empty_output(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        cb._last_tool_output = None
        cb.on_tool_end(output="", run_id=uuid4())
        assert cb._last_tool_output is None

    def test_on_tool_error_clears_output(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        cb._last_tool_output = "stale data"
        cb.on_tool_error(
            error=RuntimeError("tool failed"),
            run_id=uuid4(),
        )
        assert cb._last_tool_output is None

    def test_on_llm_start_uses_tool_output_as_context(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        cb._last_tool_output = "Retrieved document."
        run_id = uuid4()
        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["What is X?"],
            run_id=run_id,
        )
        assert cb._contexts[run_id] == "Retrieved document."
        # Tool output should be consumed
        assert cb._last_tool_output is None

    def test_on_llm_start_uses_explicit_context(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        cb._last_tool_output = "Tool output."
        run_id = uuid4()
        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["What is X?"],
            run_id=run_id,
            metadata={"context": "Explicit context."},
        )
        # Explicit context takes priority
        assert cb._contexts[run_id] == "Explicit context."

    def test_on_llm_start_none_context_when_no_tool_output(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        run_id = uuid4()
        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["What is X?"],
            run_id=run_id,
        )
        assert cb._contexts[run_id] is None

    @patch("groundlens.integrations.langgraph.callback.evaluate")
    def test_on_llm_end_evaluates_and_adds_step(
        self,
        mock_eval: MagicMock,
    ) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        mock_eval.return_value = _make_score(
            value=1.25,
            normalized=0.80,
            flagged=False,
            method="sgi",
        )

        cb = GroundlensLangGraphCallback()
        cb._current_node = "retriever"
        run_id = uuid4()

        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["What is X?"],
            run_id=run_id,
        )

        mock_response = MagicMock()
        mock_generation = MagicMock()
        mock_generation.text = "X is Y."
        mock_response.generations = [[mock_generation]]

        cb.on_llm_end(response=mock_response, run_id=run_id)

        mock_eval.assert_called_once()
        trace = cb.get_trace()
        assert trace.total_steps == 1
        assert trace.steps[0].node_name == "retriever"
        assert trace.steps[0].method == "sgi"

    @patch("groundlens.integrations.langgraph.callback.evaluate")
    def test_on_llm_end_with_tool_context_uses_sgi(
        self,
        mock_eval: MagicMock,
    ) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        mock_eval.return_value = _make_score(method="sgi")

        cb = GroundlensLangGraphCallback()
        # Simulate tool output before LLM call
        cb._last_tool_output = "Tool result data."
        run_id = uuid4()

        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["Summarize."],
            run_id=run_id,
        )
        mock_response = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "Summary."
        mock_response.generations = [[mock_gen]]

        cb.on_llm_end(response=mock_response, run_id=run_id)

        call_kwargs = mock_eval.call_args
        assert call_kwargs[1]["context"] == "Tool result data."

    @patch("groundlens.integrations.langgraph.callback.evaluate")
    def test_on_llm_end_without_context_uses_dgi(
        self,
        mock_eval: MagicMock,
    ) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        mock_eval.return_value = _make_score(method="dgi")

        cb = GroundlensLangGraphCallback()
        run_id = uuid4()

        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["What is X?"],
            run_id=run_id,
        )
        mock_response = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "X is Y."
        mock_response.generations = [[mock_gen]]

        cb.on_llm_end(response=mock_response, run_id=run_id)

        call_kwargs = mock_eval.call_args
        assert call_kwargs[1]["context"] is None

    @patch("groundlens.integrations.langgraph.callback.evaluate")
    def test_flagged_step_logged_as_warning(
        self,
        mock_eval: MagicMock,
    ) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        mock_eval.return_value = _make_score(
            value=0.18,
            normalized=0.25,
            flagged=True,
            method="dgi",
        )

        cb = GroundlensLangGraphCallback()
        run_id = uuid4()
        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["Q?"],
            run_id=run_id,
        )
        mock_response = MagicMock()
        mock_gen = MagicMock()
        mock_gen.text = "A."
        mock_response.generations = [[mock_gen]]

        cb.on_llm_end(response=mock_response, run_id=run_id)

        trace = cb.get_trace()
        assert trace.flagged_steps == 1
        assert trace.steps[0].triage == "flagged"

    def test_on_llm_error_cleans_up_state(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        run_id = uuid4()
        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["Q?"],
            run_id=run_id,
        )
        assert run_id in cb._prompts

        cb.on_llm_error(
            error=RuntimeError("LLM failed"),
            run_id=run_id,
        )
        assert run_id not in cb._prompts
        assert run_id not in cb._contexts
        assert run_id not in cb._start_times
        assert run_id not in cb._run_nodes

    def test_reset_clears_everything(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        cb._step_counter = 5
        cb._last_tool_output = "leftover"
        cb._last_tool_name = "old_tool"
        cb._current_node = "some_node"
        cb._trace.steps.append(_make_step())

        cb.reset()

        assert cb._step_counter == 0
        assert cb._last_tool_output is None
        assert cb._last_tool_name is None
        assert cb._current_node == "unknown"
        assert cb.get_trace().total_steps == 0

    @patch("groundlens.integrations.langgraph.callback.evaluate")
    def test_multi_step_trace(self, mock_eval: MagicMock) -> None:
        """Simulate a 3-step agent: tool call -> LLM (SGI) -> LLM (DGI)."""
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()

        # Step 1: Tool call provides context
        cb.on_tool_start(
            serialized={"name": "search"},
            input_str="query",
            run_id=uuid4(),
        )
        cb.on_tool_end(output="Document text.", run_id=uuid4())

        # Step 2: LLM with tool context -> SGI
        mock_eval.return_value = _make_score(
            value=1.30,
            normalized=0.85,
            flagged=False,
            method="sgi",
        )
        cb._current_node = "summarizer"
        run_id_1 = uuid4()
        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["Summarize."],
            run_id=run_id_1,
        )
        mock_resp_1 = MagicMock()
        mock_gen_1 = MagicMock()
        mock_gen_1.text = "Summary of document."
        mock_resp_1.generations = [[mock_gen_1]]
        cb.on_llm_end(response=mock_resp_1, run_id=run_id_1)

        # Step 3: LLM without context -> DGI
        mock_eval.return_value = _make_score(
            value=0.42,
            normalized=0.71,
            flagged=False,
            method="dgi",
        )
        cb._current_node = "responder"
        run_id_2 = uuid4()
        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["Answer the user."],
            run_id=run_id_2,
        )
        mock_resp_2 = MagicMock()
        mock_gen_2 = MagicMock()
        mock_gen_2.text = "Here is the answer."
        mock_resp_2.generations = [[mock_gen_2]]
        cb.on_llm_end(response=mock_resp_2, run_id=run_id_2)

        trace = cb.get_trace()
        assert trace.total_steps == 2
        assert trace.steps[0].node_name == "summarizer"
        assert trace.steps[0].method == "sgi"
        assert trace.steps[1].node_name == "responder"
        assert trace.steps[1].method == "dgi"
        assert trace.trusted_steps == 2

        # Verify summary is coherent
        summary = trace.summary()
        assert "2 steps" in summary
        assert "2 trusted" in summary

        # Verify HTML report renders
        html = trace.to_html()
        assert "summarizer" in html
        assert "responder" in html

    def test_on_llm_end_skips_empty_response(self) -> None:
        from groundlens.integrations.langgraph import (
            GroundlensLangGraphCallback,
        )

        cb = GroundlensLangGraphCallback()
        run_id = uuid4()
        cb.on_llm_start(
            serialized={"name": "gpt-4o"},
            prompts=["Q?"],
            run_id=run_id,
        )

        mock_response = MagicMock()
        mock_response.generations = []  # Empty generations

        cb.on_llm_end(response=mock_response, run_id=run_id)
        assert cb.get_trace().total_steps == 0


# ── Package __init__ ─────────────────────────────────────────────────────────


class TestPackageInit:
    """Test that the package exports are correct."""

    def test_exports(self) -> None:
        from groundlens.integrations.langgraph import (
            AgentStep,
            AgentTrace,
            GroundlensLangGraphCallback,
        )

        assert AgentStep is not None
        assert AgentTrace is not None
        assert GroundlensLangGraphCallback is not None

    def test_all_attribute(self) -> None:
        import groundlens.integrations.langgraph as pkg

        assert hasattr(pkg, "__all__")
        assert "AgentStep" in pkg.__all__
        assert "AgentTrace" in pkg.__all__
        assert "GroundlensLangGraphCallback" in pkg.__all__
