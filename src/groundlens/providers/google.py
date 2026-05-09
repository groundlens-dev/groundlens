"""Google Gemini provider with automatic groundlens hallucination scoring.

Wraps the Google Generative AI Python SDK and evaluates every response
using SGI (when context is provided) or DGI (context-free).

Example:
    >>> from groundlens.providers.google import GroundlensGemini
    >>> llm = GroundlensGemini(api_key="AI...")
    >>> resp = llm.chat("What is X?", context="X is defined as Y.")
    >>> resp.groundlens_score.flagged
    False
"""

from __future__ import annotations

import logging
from typing import Any

from groundlens.evaluate import evaluate
from groundlens.providers._base import LLMResponse

logger = logging.getLogger(__name__)


def _configure_genai(api_key: str) -> Any:
    """Lazily import and configure the Google Generative AI SDK.

    Args:
        api_key: Google AI API key.

    Returns:
        The configured ``google.generativeai`` module.

    Raises:
        ImportError: If the ``google-generativeai`` package is not installed.
    """
    try:
        import google.generativeai as _genai
    except ImportError as exc:
        msg = (
            "The 'google-generativeai' package is required for GroundlensGemini. "
            "Install it with: pip install 'groundlens[google]'"
        )
        raise ImportError(msg) from exc
    _genai.configure(api_key=api_key)
    return _genai


class GroundlensGemini:
    """Google Gemini provider with built-in groundlens scoring.

    Wraps the Google Generative AI SDK and automatically evaluates
    each response for hallucination risk.

    Args:
        api_key: Google AI API key.
        model: Gemini model to use for generation. Defaults to
            ``"gemini-2.0-flash"``.
        groundlens_model: Sentence-transformer model for groundlens scoring.
            Defaults to ``"all-MiniLM-L6-v2"``.
        groundlens_threshold: Score threshold override (reserved for future use).
            Defaults to ``0.45``.

    Example:
        >>> llm = GroundlensGemini(api_key="AI...")
        >>> resp = llm.chat("Summarize this.", context="Source text here.")
        >>> print(resp.groundlens_score.explanation)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        groundlens_model: str = "all-MiniLM-L6-v2",
        groundlens_threshold: float = 0.45,
    ) -> None:
        self._genai = _configure_genai(api_key)
        self._model_name = model
        self._generative_model = self._genai.GenerativeModel(model)
        self._groundlens_model = groundlens_model
        self._groundlens_threshold = groundlens_threshold

    def chat(
        self,
        prompt: str,
        context: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a prompt to Gemini and score the response.

        Args:
            prompt: The user message content.
            context: Optional source document. When provided, SGI scoring
                is used; otherwise DGI scoring is applied.
            **kwargs: Additional keyword arguments forwarded to the
                Gemini ``generate_content`` call.

        Returns:
            LLMResponse containing the generated text, model identifier,
            usage metadata, and a groundlens hallucination score.

        Raises:
            google.api_core.exceptions.GoogleAPIError: If the API call fails.

        Example:
            >>> llm = GroundlensGemini(api_key="AI...")
            >>> resp = llm.chat("Explain gravity.")
            >>> resp.text
            'Gravity is a fundamental force...'
        """
        logger.debug("Calling Gemini model=%s prompt_len=%d", self._model_name, len(prompt))

        response = self._generative_model.generate_content(prompt, **kwargs)

        text = response.text or ""

        usage: dict[str, Any] = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
            usage = {
                "prompt_token_count": response.usage_metadata.prompt_token_count,
                "candidates_token_count": response.usage_metadata.candidates_token_count,
                "total_token_count": response.usage_metadata.total_token_count,
            }

        score = evaluate(
            question=prompt,
            response=text,
            context=context,
            model=self._groundlens_model,
        )

        logger.info(
            "Gemini response scored: method=%s value=%.3f flagged=%s",
            score.method,
            score.value,
            score.flagged,
        )

        return LLMResponse(
            text=text,
            model=self._model_name,
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
