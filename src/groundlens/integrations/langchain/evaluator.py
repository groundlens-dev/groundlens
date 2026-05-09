"""LangSmith run evaluator for groundlens hallucination scoring.

Implements the LangSmith ``RunEvaluator`` protocol to enable groundlens
scoring as part of LangSmith experiment evaluation pipelines.

Example:
    >>> from groundlens.integrations.langchain import GroundlensEvaluator
    >>> evaluator = GroundlensEvaluator()
    >>> # Use with LangSmith evaluate()
    >>> from langsmith import evaluate as ls_evaluate
    >>> ls_evaluate(my_chain, data="my-dataset", evaluators=[evaluator])
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from groundlens.evaluate import evaluate

if TYPE_CHECKING:
    from langsmith.schemas import Example, Run

    from groundlens.score import GroundlensScore

logger = logging.getLogger(__name__)


def _import_langsmith_types() -> tuple[type, ...]:
    """Lazily import langsmith evaluation types.

    Returns:
        Tuple of imported types for reference.

    Raises:
        ImportError: If the ``langsmith`` package is not installed.
    """
    try:
        from langsmith.evaluation import EvaluationResult
    except ImportError as exc:
        msg = (
            "The 'langsmith' package is required for GroundlensEvaluator. "
            "Install it with: pip install 'groundlens[langchain]'"
        )
        raise ImportError(msg) from exc
    return (EvaluationResult,)


class GroundlensEvaluator:
    """LangSmith run evaluator that scores outputs with groundlens.

    Extracts input, output, and optional context from LangSmith runs
    and examples, then computes SGI (when context is available) or
    DGI (context-free) scores.

    Args:
        groundlens_model: Sentence-transformer model for groundlens scoring.
            Defaults to ``"all-MiniLM-L6-v2"``.
        input_key: Key to extract the question from run inputs.
            Defaults to ``"question"``.
        output_key: Key to extract the response from run outputs.
            Defaults to ``"output"``.
        context_key: Key to extract context from example inputs.
            Defaults to ``"context"``.

    Example:
        >>> evaluator = GroundlensEvaluator()
        >>> # Typically used with LangSmith evaluate():
        >>> # from langsmith import evaluate
        >>> # evaluate(chain, data="dataset", evaluators=[evaluator])
    """

    def __init__(
        self,
        groundlens_model: str = "all-MiniLM-L6-v2",
        input_key: str = "question",
        output_key: str = "output",
        context_key: str = "context",
    ) -> None:
        self._groundlens_model = groundlens_model
        self._input_key = input_key
        self._output_key = output_key
        self._context_key = context_key

    def evaluate_run(
        self,
        run: Run,
        example: Example | None = None,
    ) -> Any:
        """Evaluate a LangSmith run for hallucination risk.

        Extracts the question from run inputs, the response from run
        outputs, and optionally context from the example inputs. Returns
        a LangSmith ``EvaluationResult`` with the groundlens score.

        Args:
            run: The LangSmith run to evaluate. Must have ``inputs``
                and ``outputs`` dicts.
            example: Optional LangSmith example providing ground truth
                or context for SGI evaluation.

        Returns:
            An ``EvaluationResult`` with key ``"groundlens"``, the normalized
            score, and a comment containing the explanation.

        Example:
            >>> evaluator = GroundlensEvaluator()
            >>> result = evaluator.evaluate_run(run, example)
            >>> result.key
            'groundlens'
        """
        (evaluation_result_cls,) = _import_langsmith_types()

        inputs = run.inputs or {}
        outputs = run.outputs or {}

        question = inputs.get(self._input_key, "")
        response = outputs.get(self._output_key, "")

        if not question:
            for key in ("input", "query", "prompt"):
                question = inputs.get(key, "")
                if question:
                    break

        if not response:
            for key in ("answer", "result", "text", "response"):
                response = outputs.get(key, "")
                if response:
                    break

        context: str | None = None
        if example is not None and example.inputs:
            context = example.inputs.get(self._context_key)

        if not question or not response:
            logger.warning(
                "GroundlensEvaluator: missing question or response for run %s",
                run.id,
            )
            return evaluation_result_cls(
                key="groundlens",
                score=None,
                comment="Missing question or response — could not evaluate.",
            )

        score: GroundlensScore = evaluate(
            question=str(question),
            response=str(response),
            context=str(context) if context else None,
            model=self._groundlens_model,
        )

        logger.info(
            "GroundlensEvaluator run=%s method=%s value=%.3f flagged=%s",
            run.id,
            score.method,
            score.value,
            score.flagged,
        )

        return evaluation_result_cls(
            key="groundlens",
            score=score.normalized,
            comment=score.explanation,
        )
