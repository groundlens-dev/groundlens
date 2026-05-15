"""LangGraph-aware callback handler for automatic groundlens scoring.

Extends the base LangChain callback with graph-level awareness:

- Tracks which LangGraph node produced each LLM call.
- Extracts tool outputs as grounding context for SGI scoring.
- Builds a structured execution trace with triage classification.
- Supports the full LangGraph execution lifecycle.

When a tool call returns data and the next LLM call uses it, the tool
output automatically becomes the context for SGI (grounded) scoring.
When no tool context is available, DGI (ungrounded) scoring is used.

Example:
    >>> from langgraph.graph import StateGraph
    >>> from groundlens.integrations.langgraph import GroundlensLangGraphCallback
    >>>
    >>> gl = GroundlensLangGraphCallback()
    >>> result = app.invoke({"question": "..."}, config={"callbacks": [gl]})
    >>>
    >>> trace = gl.get_trace()
    >>> print(trace.summary())
    >>> trace.to_html("report.html")
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from groundlens.evaluate import evaluate
from groundlens.integrations.langgraph.trace import AgentStep, AgentTrace, _triage_label

if TYPE_CHECKING:
    from uuid import UUID

    from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


class GroundlensLangGraphCallback:
    """LangGraph callback that scores every LLM response and builds a triage trace.

    This callback intercepts LLM calls within a LangGraph execution,
    evaluates each response with groundlens (SGI when tool context is
    available, DGI otherwise), and accumulates results into a structured
    :class:`AgentTrace`.

    **Auto context detection:** If a tool call produced output before an
    LLM call, that output is used as grounding context (SGI). If no tool
    output is available, DGI scoring is applied automatically.

    Args:
        groundlens_model: Sentence-transformer model for scoring.
            Defaults to ``"all-MiniLM-L6-v2"``.
        context_key: Metadata key for explicit context override.
            Defaults to ``"context"``.

    Example:
        >>> from groundlens.integrations.langgraph import GroundlensLangGraphCallback
        >>> gl = GroundlensLangGraphCallback()
        >>> result = app.invoke(input, config={"callbacks": [gl]})
        >>> trace = gl.get_trace()
        >>> print(trace.summary())
        Agent completed: 3 steps (523ms)
        \u2713 2 trusted  \u26a0 0 review  \u2717 1 flagged
        Flagged: fact_check (DGI=0.180)
    """

    def __init__(
        self,
        groundlens_model: str = "all-MiniLM-L6-v2",
        context_key: str = "context",
    ) -> None:
        self._groundlens_model = groundlens_model
        self._context_key = context_key

        # Per-run state
        self._prompts: dict[UUID, list[str]] = {}
        self._contexts: dict[UUID, str | None] = {}
        self._start_times: dict[UUID, float] = {}
        self._run_nodes: dict[UUID, str] = {}

        # Tool output accumulator
        self._last_tool_output: str | None = None
        self._last_tool_name: str | None = None

        # Current graph node tracking
        self._current_node: str = "unknown"

        # The trace being built
        self._trace = AgentTrace()
        self._step_counter = 0

    # ── LangGraph lifecycle hooks ─────────────────────────────────────────

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any] | Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Track the current graph node when a chain starts."""
        tags = tags or []
        metadata = metadata or {}

        node = metadata.get("langgraph_node")

        if not node:
            name = serialized.get("name", "")
            if name and name not in ("RunnableSequence", "RunnableLambda", "LangGraph"):
                node = name

        if node:
            self._current_node = node
            logger.debug("on_chain_start node=%s run_id=%s", node, run_id)

    def on_chain_end(
        self,
        outputs: dict[str, Any] | Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Handle chain completion."""
        logger.debug("on_chain_end run_id=%s", run_id)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Handle chain errors."""
        logger.error("on_chain_error run_id=%s error=%s", run_id, error)

    # ── Tool hooks ────────────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Record when a tool call begins."""
        tool_name = serialized.get("name", "unknown_tool")
        self._last_tool_name = tool_name
        logger.debug("on_tool_start tool=%s run_id=%s", tool_name, run_id)

    def on_tool_end(
        self,
        output: str | Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Capture tool output as potential context for the next LLM call."""
        output_str = str(output) if output is not None else None
        if output_str and output_str.strip():
            self._last_tool_output = output_str
            logger.debug(
                "on_tool_end tool=%s output_len=%d run_id=%s",
                self._last_tool_name,
                len(output_str),
                run_id,
            )
        else:
            logger.debug(
                "on_tool_end tool=%s empty_output run_id=%s",
                self._last_tool_name, run_id,
            )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Handle tool errors."""
        self._last_tool_output = None
        logger.error("on_tool_error run_id=%s error=%s", run_id, error)

    # ── LLM hooks ─────────────────────────────────────────────────────────

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Store prompt and start timer when an LLM call begins.

        Context is resolved in this order:
        1. Explicit context from metadata.
        2. Tool output from the most recent tool call.
        3. None (triggers DGI scoring).
        """
        self._prompts[run_id] = prompts
        self._start_times[run_id] = time.monotonic()
        self._run_nodes[run_id] = self._current_node

        metadata = kwargs.get("metadata") or {}
        explicit_context = metadata.get(self._context_key)

        if explicit_context:
            self._contexts[run_id] = explicit_context
        elif self._last_tool_output:
            self._contexts[run_id] = self._last_tool_output
            self._last_tool_output = None
        else:
            self._contexts[run_id] = None

        logger.debug(
            "on_llm_start node=%s run_id=%s context=%s prompts=%d",
            self._current_node,
            run_id,
            "sgi" if self._contexts[run_id] else "dgi",
            len(prompts),
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Evaluate the LLM response and add it to the trace."""
        prompts = self._prompts.pop(run_id, [])
        context = self._contexts.pop(run_id, None)
        start_time = self._start_times.pop(run_id, time.monotonic())
        node_name = self._run_nodes.pop(run_id, "unknown")

        duration_ms = (time.monotonic() - start_time) * 1000

        if not prompts or not response.generations:
            logger.debug("on_llm_end run_id=%s — no prompts or generations", run_id)
            return

        prompt = prompts[0]
        generation = response.generations[0]
        if not generation:
            return

        text = generation[0].text

        score = evaluate(
            question=prompt,
            response=text,
            context=context,
            model=self._groundlens_model,
        )

        triage = _triage_label(score)

        step = AgentStep(
            node_name=node_name,
            step_index=self._step_counter,
            input_text=prompt,
            output_text=text,
            context=context,
            score=score,
            triage=triage,
            method=score.method,
            duration_ms=duration_ms,
        )
        self._trace.steps.append(step)
        self._step_counter += 1

        if score.flagged:
            logger.warning(
                "Groundlens FLAGGED node=%s method=%s value=%.3f triage=%s — %s",
                node_name,
                score.method,
                score.value,
                triage,
                score.explanation,
            )
        else:
            logger.info(
                "Groundlens OK node=%s method=%s value=%.3f triage=%s",
                node_name,
                score.method,
                score.value,
                triage,
            )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Clean up state when an LLM call fails."""
        self._prompts.pop(run_id, None)
        self._contexts.pop(run_id, None)
        self._start_times.pop(run_id, None)
        self._run_nodes.pop(run_id, None)
        logger.error("on_llm_error run_id=%s error=%s", run_id, error)

    # ── Public API ────────────────────────────────────────────────────────

    def get_trace(self) -> AgentTrace:
        """Return the accumulated agent execution trace."""
        return self._trace

    def reset(self) -> None:
        """Reset the callback state for a new execution."""
        self._trace = AgentTrace()
        self._step_counter = 0
        self._prompts.clear()
        self._contexts.clear()
        self._start_times.clear()
        self._run_nodes.clear()
        self._last_tool_output = None
        self._last_tool_name = None
        self._current_node = "unknown"
