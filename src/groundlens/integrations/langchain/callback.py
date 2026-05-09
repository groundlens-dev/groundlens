"""LangChain callback handler for automatic groundlens scoring.

Intercepts LLM calls during chain execution and evaluates each response
for hallucination risk. Flagged outputs generate log warnings.

Example:
    >>> from groundlens.integrations.langchain import GroundlensCallback
    >>> from langchain_openai import ChatOpenAI
    >>> cb = GroundlensCallback()
    >>> llm = ChatOpenAI(callbacks=[cb])
    >>> llm.invoke("What is the capital of France?")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from groundlens.evaluate import evaluate

if TYPE_CHECKING:
    from uuid import UUID

    from langchain_core.outputs import LLMResult

    from groundlens.score import GroundlensScore

logger = logging.getLogger(__name__)


class GroundlensCallback:
    """LangChain callback handler that scores every LLM response with groundlens.

    Stores prompts on ``on_llm_start`` and evaluates responses on
    ``on_llm_end``. Flagged results are logged as warnings. Scores
    are accumulated in :attr:`scores` for later inspection.

    Args:
        groundlens_model: Sentence-transformer model for groundlens scoring.
            Defaults to ``"all-MiniLM-L6-v2"``.
        context_key: Metadata key to look for context in ``kwargs``.
            Defaults to ``"context"``.

    Example:
        >>> cb = GroundlensCallback()
        >>> # Use as a LangChain callback
        >>> from langchain_openai import ChatOpenAI
        >>> llm = ChatOpenAI(callbacks=[cb])
        >>> result = llm.invoke("Summarize the document.")
        >>> # Inspect scores after execution
        >>> for run_id, score in cb.scores.items():
        ...     print(f"{run_id}: {score.explanation}")
    """

    def __init__(
        self,
        groundlens_model: str = "all-MiniLM-L6-v2",
        context_key: str = "context",
    ) -> None:
        self._groundlens_model = groundlens_model
        self._context_key = context_key
        self._prompts: dict[UUID, list[str]] = {}
        self._contexts: dict[UUID, str | None] = {}
        self.scores: dict[UUID, GroundlensScore] = {}

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Store prompts when an LLM call begins.

        Args:
            serialized: Serialized LLM configuration.
            prompts: List of prompt strings sent to the LLM.
            run_id: Unique identifier for this LLM run.
            **kwargs: Additional keyword arguments from LangChain.
        """
        self._prompts[run_id] = prompts
        metadata = kwargs.get("metadata") or {}
        self._contexts[run_id] = metadata.get(self._context_key)
        logger.debug("on_llm_start run_id=%s prompts=%d", run_id, len(prompts))

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Evaluate the LLM response for hallucination risk.

        Args:
            response: The LLM result containing generated text.
            run_id: Unique identifier for this LLM run.
            **kwargs: Additional keyword arguments from LangChain.
        """
        prompts = self._prompts.pop(run_id, [])
        context = self._contexts.pop(run_id, None)

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

        self.scores[run_id] = score

        if score.flagged:
            logger.warning(
                "Groundlens FLAGGED run_id=%s method=%s value=%.3f — %s",
                run_id,
                score.method,
                score.value,
                score.explanation,
            )
        else:
            logger.info(
                "Groundlens OK run_id=%s method=%s value=%.3f",
                run_id,
                score.method,
                score.value,
            )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Clean up state when an LLM call fails.

        Args:
            error: The exception that caused the LLM call to fail.
            run_id: Unique identifier for this LLM run.
            **kwargs: Additional keyword arguments from LangChain.
        """
        self._prompts.pop(run_id, None)
        self._contexts.pop(run_id, None)
        logger.error("on_llm_error run_id=%s error=%s", run_id, error)
