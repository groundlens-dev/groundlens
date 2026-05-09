"""Semantic Kernel function invocation filter for groundlens.

Intercepts function results and evaluates them for hallucination risk.
The filter attaches groundlens scores to the invocation context metadata.

Example:
    >>> from groundlens.integrations.semantic_kernel import GroundlensFilter
    >>> filt = GroundlensFilter()
    >>> # Register with Semantic Kernel
    >>> kernel.add_filter("function_invocation", filt)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from groundlens.evaluate import evaluate

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from groundlens.score import GroundlensScore

logger = logging.getLogger(__name__)


def _validate_semantic_kernel_available() -> None:
    """Verify that the semantic-kernel package is importable.

    Raises:
        ImportError: If the ``semantic-kernel`` package is not installed.
    """
    try:
        import semantic_kernel  # noqa: F401
    except ImportError as exc:
        msg = (
            "The 'semantic-kernel' package is required for GroundlensFilter. "
            "Install it with: pip install 'groundlens[semantic-kernel]'"
        )
        raise ImportError(msg) from exc


class GroundlensFilter:
    """Semantic Kernel function invocation filter with groundlens scoring.

    Intercepts function invocation results and evaluates them for
    hallucination risk. Scores are attached to the invocation context
    metadata under the ``"groundlens_score"`` key and stored in
    :attr:`scores` for later inspection.

    Args:
        groundlens_model: Sentence-transformer model for groundlens scoring.
            Defaults to ``"all-MiniLM-L6-v2"``.
        input_key: Key to extract the question from function arguments.
            Defaults to ``"input"``.
        context_key: Key to extract context from function arguments.
            Defaults to ``"context"``.

    Example:
        >>> filt = GroundlensFilter()
        >>> # Register with a Semantic Kernel instance
        >>> kernel.add_filter("function_invocation", filt)
        >>> # After invocation, inspect scores:
        >>> for fn_name, score in filt.scores:
        ...     print(f"{fn_name}: {score.explanation}")
    """

    def __init__(
        self,
        groundlens_model: str = "all-MiniLM-L6-v2",
        input_key: str = "input",
        context_key: str = "context",
    ) -> None:
        self._groundlens_model = groundlens_model
        self._input_key = input_key
        self._context_key = context_key
        self.scores: list[tuple[str, GroundlensScore]] = []

    async def on_function_invocation(
        self,
        context: Any,
        next_handler: Callable[..., Awaitable[None]],
    ) -> None:
        """Intercept a function invocation and evaluate the result.

        Calls the next filter/function in the pipeline, then evaluates
        the result with groundlens. Attaches the score to the context
        metadata.

        Args:
            context: The Semantic Kernel ``FunctionInvocationContext``
                containing function arguments and result.
            next_handler: The next handler in the filter pipeline.

        Example:
            >>> # This method is called automatically by Semantic Kernel
            >>> # when registered as a function invocation filter.
        """
        await next_handler(context)

        function_name = getattr(context, "function_name", "unknown")
        arguments = getattr(context, "arguments", {}) or {}
        result = getattr(context, "result", None)

        if result is None:
            logger.debug("GroundlensFilter: no result for function %s", function_name)
            return

        result_value = getattr(result, "value", None)
        result_value = str(result) if result_value is None else str(result_value)

        question = str(arguments.get(self._input_key, ""))
        context_text: str | None = arguments.get(self._context_key)
        if context_text is not None:
            context_text = str(context_text)

        if not question:
            logger.debug(
                "GroundlensFilter: no input found for function %s, skipping",
                function_name,
            )
            return

        score: GroundlensScore = evaluate(
            question=question,
            response=result_value,
            context=context_text,
            model=self._groundlens_model,
        )

        self.scores.append((function_name, score))

        metadata = getattr(context, "metadata", None)
        if metadata is not None and isinstance(metadata, dict):
            metadata["groundlens_score"] = score

        if score.flagged:
            logger.warning(
                "GroundlensFilter FLAGGED function=%s method=%s value=%.3f — %s",
                function_name,
                score.method,
                score.value,
                score.explanation,
            )
        else:
            logger.info(
                "GroundlensFilter OK function=%s method=%s value=%.3f",
                function_name,
                score.method,
                score.value,
            )
