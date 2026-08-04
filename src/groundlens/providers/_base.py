"""Base types and protocol for groundlens LLM providers.

Defines the ``LLMResponse`` dataclass returned by all providers, the
``BaseLLMProvider`` protocol that every concrete provider must satisfy, and
the shared scoring guard the concrete providers call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from groundlens.evaluate import evaluate

if TYPE_CHECKING:
    from groundlens.score import GroundlensScore

logger = logging.getLogger(__name__)


def _score_or_none(
    text: str,
    prompt: str,
    context: str | None,
    groundlens_model: str,
    provider: str,
) -> GroundlensScore | None:
    """Score a completion, returning ``None`` when there is nothing to score.

    An LLM turn legitimately carries no text: a tool-call-only response, a
    content-filter block, a zero-length completion, a stop before the first
    token. ``compute_sgi`` / ``compute_dgi`` reject an empty ``response`` with
    a ``ValueError``, so scoring one unconditionally turned a normal provider
    outcome into an exception raised from the scoring layer — with a message
    about groundlens, not about the model call the user actually made.

    Args:
        text: The completion text, possibly empty.
        prompt: The user prompt, used as the question.
        context: Optional source document (selects SGI over DGI).
        groundlens_model: Sentence-transformer model for scoring.
        provider: Provider name, for the log line.

    Returns:
        The :class:`~groundlens.score.GroundlensScore`, or ``None`` when
        ``text`` is empty or whitespace.
    """
    if not text.strip():
        logger.info(
            "%s returned an empty completion; skipping groundlens scoring.",
            provider,
        )
        return None

    score = evaluate(
        question=prompt,
        response=text,
        context=context,
        model=groundlens_model,
    )
    logger.info(
        "%s response scored: method=%s value=%.3f flagged=%s",
        provider,
        score.method,
        score.value,
        score.flagged,
    )
    return score


@dataclass(slots=True)
class LLMResponse:
    """Unified response container for all LLM provider calls.

    Attributes:
        text: The generated text content from the LLM.
        model: The model identifier used for generation.
        usage: Provider-specific usage metadata (tokens, cost, etc.).
        groundlens_score: Optional groundlens evaluation result attached
            after hallucination scoring.

    Example:
        >>> resp = LLMResponse(text="Hello!", model="gpt-4o", usage={})
        >>> resp.groundlens_score is None
        True
    """

    text: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    groundlens_score: GroundlensScore | None = None


@runtime_checkable
class BaseLLMProvider(Protocol):
    """Protocol defining the interface all groundlens providers implement.

    Providers wrap third-party LLM SDKs and automatically attach a
    ``GroundlensScore`` to every response, enabling inline hallucination
    detection without changing application code.

    Example:
        >>> def use_provider(provider: BaseLLMProvider) -> None:
        ...     resp = provider.complete("Summarize this.", context="Source text.")
        ...     if resp.groundlens_score and resp.groundlens_score.flagged:
        ...         print("Review recommended!")
    """

    def complete(
        self,
        prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        """Generate a completion for the given prompt.

        Args:
            prompt: The user prompt or instruction.
            context: Optional source document for grounded evaluation.
                When provided, SGI scoring is used; otherwise DGI.

        Returns:
            LLMResponse with generated text and groundlens score.
        """
        ...

    def chat(
        self,
        messages: list[dict[str, str]],
        context: str | None = None,
    ) -> LLMResponse:
        """Generate a chat completion from a message history.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            context: Optional source document for grounded evaluation.
                When provided, SGI scoring is used; otherwise DGI.

        Returns:
            LLMResponse with generated text and groundlens score.
        """
        ...
