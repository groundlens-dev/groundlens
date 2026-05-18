"""LangGraph integration for groundlens hallucination triage.

Provides a callback handler that monitors every LLM call in a LangGraph
agent pipeline, automatically triages hallucinations (SGI for grounded
outputs, DGI for ungrounded), and produces structured execution traces
with visual reports.

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

from groundlens.integrations.langgraph.trace import AgentStep, AgentTrace

__all__ = [
    "AgentStep",
    "AgentTrace",
    "GroundlensLangGraphCallback",
]


def __getattr__(name: str) -> object:  # noqa: ANN401
    """Lazy-import GroundlensLangGraphCallback to avoid hard dep on langchain_core."""
    if name == "GroundlensLangGraphCallback":
        from groundlens.integrations.langgraph.callback import GroundlensLangGraphCallback

        return GroundlensLangGraphCallback
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
