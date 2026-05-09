"""Semantic Grounding Index (SGI) — grounded hallucination detection.

SGI evaluates whether an LLM response engaged with provided source
context or stayed semantically anchored to the question. It requires
three inputs: question, context, and response.

Mathematical formulation:

    SGI = dist(phi(response), phi(question)) / dist(phi(response), phi(context))

where phi is the sentence embedding function and dist is Euclidean distance
in the embedding space R^n.

Geometric interpretation:

    - SGI > 1: response is closer to context than to question (grounded).
    - SGI < 1: response is closer to question than to context (risk).
    - SGI = 1: response is equidistant (ambiguous).

Use cases:

    - RAG pipeline verification: check that retrieved context was used.
    - Document Q&A: verify answers cite the source material.
    - Summarization: confirm the summary reflects the input document.

References:
    Marin (2025). *Semantic Grounding Index for LLM Hallucination Detection*.
    arXiv:2512.13771.
"""

from __future__ import annotations

import logging

from groundlens._internal.embeddings import DEFAULT_MODEL, encode_texts
from groundlens._internal.geometry import euclidean_distance
from groundlens._internal.thresholds import SGI_REVIEW, normalize_sgi
from groundlens.score import SGIResult

logger = logging.getLogger(__name__)


def compute_sgi(
    question: str,
    context: str,
    response: str,
    *,
    model: str = DEFAULT_MODEL,
) -> SGIResult:
    """Compute the Semantic Grounding Index for a response.

    Args:
        question: The input query.
        context: Source document, retrieved chunks, or reference text.
        response: The LLM output to evaluate.
        model: Sentence transformer model name. Default ``all-MiniLM-L6-v2``.

    Returns:
        SGIResult with raw score, normalized score, and flag status.

    Raises:
        ValueError: If any input string is empty.

    Example:
        >>> from groundlens import compute_sgi
        >>> result = compute_sgi(
        ...     question="What is the capital of France?",
        ...     context="France is in Western Europe. Its capital is Paris.",
        ...     response="The capital of France is Paris.",
        ... )
        >>> result.flagged
        False
    """
    if not question.strip():
        msg = "question must be a non-empty string."
        raise ValueError(msg)
    if not context.strip():
        msg = "context must be a non-empty string."
        raise ValueError(msg)
    if not response.strip():
        msg = "response must be a non-empty string."
        raise ValueError(msg)

    embeddings = encode_texts([question, context, response], model_name=model)
    q_emb, ctx_emb, resp_emb = embeddings[0], embeddings[1], embeddings[2]

    q_dist = euclidean_distance(resp_emb, q_emb)
    ctx_dist = euclidean_distance(resp_emb, ctx_emb)

    # Degenerate case: response identical to context.
    if ctx_dist < 1e-8:
        return SGIResult(
            value=10.0,
            normalized=1.0,
            flagged=False,
            q_dist=round(q_dist, 4),
            ctx_dist=round(ctx_dist, 4),
        )

    # Degenerate case: response identical to question.
    if q_dist < 1e-8:
        return SGIResult(
            value=0.0,
            normalized=0.0,
            flagged=True,
            q_dist=round(q_dist, 4),
            ctx_dist=round(ctx_dist, 4),
        )

    raw = q_dist / ctx_dist
    normalized = normalize_sgi(raw)

    return SGIResult(
        value=round(raw, 4),
        normalized=round(normalized, 4),
        flagged=raw < SGI_REVIEW,
        q_dist=round(q_dist, 4),
        ctx_dist=round(ctx_dist, 4),
    )


class SGI:
    """Reusable SGI scorer with a pre-configured embedding model.

    Use this class when evaluating multiple responses with the same model
    to avoid repeating the ``model`` parameter.

    Example:
        >>> sgi = SGI(model="all-MiniLM-L6-v2")
        >>> result = sgi.score(
        ...     question="What is X?",
        ...     context="X is Y.",
        ...     response="X is Y.",
        ... )
        >>> result.flagged
        False
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialize SGI scorer.

        Args:
            model: Sentence transformer model name or path.
        """
        self.model = model

    def score(
        self,
        question: str,
        context: str,
        response: str,
    ) -> SGIResult:
        """Compute SGI for a single response.

        Args:
            question: The input query.
            context: Source document or reference text.
            response: The LLM output to evaluate.

        Returns:
            SGIResult with score and flag status.
        """
        return compute_sgi(
            question=question,
            context=context,
            response=response,
            model=self.model,
        )
