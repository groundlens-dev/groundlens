"""OpenAI provider with automatic groundlens hallucination scoring.

Wraps the OpenAI Python SDK and evaluates every response using SGI
(when context is provided) or DGI (context-free).

Example:
    >>> from groundlens.providers.openai import GroundlensOpenAI
    >>> llm = GroundlensOpenAI(api_key="sk-...")
    >>> resp = llm.chat("What is the capital of France?", context="Paris is the capital.")
    >>> resp.groundlens_score.flagged
    False
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from groundlens.evaluate import evaluate
from groundlens.providers._base import LLMResponse

if TYPE_CHECKING:
    import openai

logger = logging.getLogger(__name__)


def _get_openai_client(api_key: str) -> openai.OpenAI:
    """Lazily import and instantiate the OpenAI client.

    Args:
        api_key: OpenAI API key.

    Returns:
        An authenticated ``openai.OpenAI`` client instance.

    Raises:
        ImportError: If the ``openai`` package is not installed.
    """
    try:
        import openai as _openai
    except ImportError as exc:
        msg = (
            "The 'openai' package is required for GroundlensOpenAI. "
            "Install it with: pip install 'groundlens[openai]'"
        )
        raise ImportError(msg) from exc
    return _openai.OpenAI(api_key=api_key)


class GroundlensOpenAI:
    """OpenAI LLM provider with built-in groundlens scoring.

    Wraps the OpenAI chat completions API and automatically evaluates
    each response for hallucination risk.

    Args:
        api_key: OpenAI API key.
        model: Chat model to use for generation. Defaults to ``"gpt-4o"``.
        groundlens_model: Sentence-transformer model for groundlens scoring.
            Defaults to ``"all-MiniLM-L6-v2"``.
        groundlens_threshold: Score threshold override (reserved for future use).
            Defaults to ``0.45``.

    Example:
        >>> llm = GroundlensOpenAI(api_key="sk-...")
        >>> resp = llm.chat("Summarize this document.", context="The document text.")
        >>> print(resp.groundlens_score.explanation)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        groundlens_model: str = "all-MiniLM-L6-v2",
        groundlens_threshold: float = 0.45,
    ) -> None:
        self._client = _get_openai_client(api_key)
        self._model = model
        self._groundlens_model = groundlens_model
        self._groundlens_threshold = groundlens_threshold

    def chat(
        self,
        prompt: str,
        context: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request and score the response.

        Args:
            prompt: The user message content.
            context: Optional source document. When provided, SGI scoring
                is used; otherwise DGI scoring is applied.
            **kwargs: Additional keyword arguments forwarded to the
                OpenAI ``chat.completions.create`` call.

        Returns:
            LLMResponse containing the generated text, model identifier,
            usage metadata, and a groundlens hallucination score.

        Raises:
            openai.OpenAIError: If the API call fails.

        Example:
            >>> llm = GroundlensOpenAI(api_key="sk-...")
            >>> resp = llm.chat("What causes tides?")
            >>> resp.text
            'Tides are primarily caused by...'
        """
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]

        logger.debug("Calling OpenAI model=%s prompt_len=%d", self._model, len(prompt))

        completion = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            **kwargs,
        )

        choice = completion.choices[0]
        text = choice.message.content or ""

        usage: dict[str, Any] = {}
        if completion.usage is not None:
            usage = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            }

        score = evaluate(
            question=prompt,
            response=text,
            context=context,
            model=self._groundlens_model,
        )

        logger.info(
            "OpenAI response scored: method=%s value=%.3f flagged=%s",
            score.method,
            score.value,
            score.flagged,
        )

        return LLMResponse(
            text=text,
            model=self._model,
            usage=usage,
            groundlens_score=score,
        )

    def complete(
        self,
        prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        """Generate a completion for the given prompt.

        Convenience method that delegates to :meth:`chat`.

        Args:
            prompt: The user prompt or instruction.
            context: Optional source document for grounded evaluation.

        Returns:
            LLMResponse with generated text and groundlens score.
        """
        return self.chat(prompt, context=context)
