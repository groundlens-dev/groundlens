"""High-level evaluation API for single and batch scoring.

This module provides convenience functions that auto-select the appropriate
scoring method (SGI if context is provided, DGI otherwise) and return
unified ``GroundlensScore`` results.

Example:
    >>> from groundlens import evaluate
    >>> score = evaluate(
    ...     question="What is X?",
    ...     response="X is Y.",
    ...     context="According to the manual, X is Y.",
    ... )
    >>> score.flagged
    False
    >>> score.method
    'sgi'
"""

from __future__ import annotations

import logging

from groundlens._internal.embeddings import DEFAULT_MODEL
from groundlens.dgi import compute_dgi
from groundlens.score import DGIResult, GroundlensScore, SGIResult
from groundlens.sgi import compute_sgi

logger = logging.getLogger(__name__)


def evaluate(
    question: str,
    response: str,
    context: str | None = None,
    *,
    model: str = DEFAULT_MODEL,
    reference_csv: str | None = None,
) -> GroundlensScore:
    """Evaluate a single LLM response for hallucination risk.

    Auto-selects scoring method:
        - **SGI** when ``context`` is provided (grounded verification).
        - **DGI** when ``context`` is ``None`` (context-free verification).

    Args:
        question: The input query.
        response: The LLM output to evaluate.
        context: Source document or retrieved text. If provided, SGI is used.
        model: Sentence transformer model name.
        reference_csv: DGI calibration CSV path (only used when context is None).

    Returns:
        GroundlensScore with method, value, flag, and explanation.

    Example:
        >>> from groundlens import evaluate
        >>> # With context → SGI
        >>> score = evaluate("Q?", "A.", context="Source text.")
        >>> score.method
        'sgi'
        >>> # Without context → DGI
        >>> score = evaluate("Q?", "A.")
        >>> score.method
        'dgi'
    """
    result: SGIResult | DGIResult
    if context is not None and context.strip():
        result = compute_sgi(
            question=question,
            context=context,
            response=response,
            model=model,
        )
    else:
        result = compute_dgi(
            question=question,
            response=response,
            model=model,
            reference_csv=reference_csv,
        )

    return GroundlensScore(
        value=result.value,
        normalized=result.normalized,
        flagged=result.flagged,
        method=result.method,
        explanation=result.explanation,
        detail=result,
    )


def evaluate_batch(
    items: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    reference_csv: str | None = None,
) -> list[GroundlensScore]:
    """Evaluate a batch of LLM responses.

    Each item in the list is a dict with keys:
        - ``question`` (required)
        - ``response`` (required)
        - ``context`` (optional — triggers SGI when present)

    Args:
        items: List of dicts, each containing question, response, and
            optionally context.
        model: Sentence transformer model name.
        reference_csv: DGI calibration CSV path.

    Returns:
        List of GroundlensScore results, one per input item.

    Raises:
        KeyError: If any item is missing ``question`` or ``response``.

    Example:
        >>> from groundlens import evaluate_batch
        >>> items = [
        ...     {"question": "Q1?", "response": "A1.", "context": "C1."},
        ...     {"question": "Q2?", "response": "A2."},
        ... ]
        >>> results = evaluate_batch(items)
        >>> len(results)
        2
    """
    results: list[GroundlensScore] = []

    for i, item in enumerate(items):
        if "question" not in item:
            msg = f"Item {i} missing required key 'question'."
            raise KeyError(msg)
        if "response" not in item:
            msg = f"Item {i} missing required key 'response'."
            raise KeyError(msg)

        score = evaluate(
            question=item["question"],
            response=item["response"],
            context=item.get("context"),
            model=model,
            reference_csv=reference_csv,
        )
        results.append(score)

    logger.info(
        "Evaluated %d items (%d flagged).", len(results), sum(1 for r in results if r.flagged)
    )

    return results
