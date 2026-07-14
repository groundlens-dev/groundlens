"""Semantic Grounding Index (SGI) — grounded hallucination detection.

SGI evaluates whether an LLM response engaged with provided source
context or stayed semantically anchored to the question. It requires
three inputs: question, context, and response.

Mathematical formulation (paper canonical, arXiv:2512.13771 Algorithm 1):

    SGI = theta(r, q) / theta(r, c)
        = arccos(r_hat . q_hat) / arccos(r_hat . c_hat)

where r_hat, q_hat, c_hat are L2-normalized sentence embeddings on the unit
hypersphere S^(d-1), and theta is the geodesic (angular) distance.

Geometric interpretation:

    - SGI > 1: response is angularly closer to context than to question (grounded).
    - SGI < 1: response is angularly closer to question than to context (risk).
    - SGI = 1: response is equidistant (ambiguous).

Use cases:

    - RAG pipeline verification: check that retrieved context was used.
    - Document Q&A: verify answers cite the source material.
    - Summarization: confirm the summary reflects the input document.

HaluEval QA (n=5,000), AUC 0.806 averaged across five embedding
architectures. This figure predates the authorship and length controls and
has not been re-run under them: treat it as provisional.

At chance on TruthfulQA. Angular geometry measures topical engagement and
provenance, not factual truth, and its skill declines toward chance as an
error stays in the register of a correct answer.

References:
    Marin (2025). *Semantic Grounding Index: Geometric Bounds on Context
        Engagement in RAG Systems*. arXiv:2512.13771.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import numpy as np

from groundlens._internal.embeddings import DEFAULT_MODEL, encode_texts
from groundlens._internal.thresholds import (
    SGI_REVIEW,
    _warn_default_thresholds_with_custom_encoder,
    normalize_sgi,
)
from groundlens.score import SGIResult

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from groundlens._internal.embeddings import EmbeddingFn

logger = logging.getLogger(__name__)

_EPS = 1e-8


def _angular_distance(a: NDArray[np.float32], b: NDArray[np.float32]) -> float:
    """Geodesic distance on the unit hypersphere.

    Assumes a and b are L2-normalized vectors. Returns arccos(a . b),
    clipped to [-1, 1] for numerical safety. The result lies in [0, pi].
    """
    dot = float(np.dot(a, b))
    dot = max(-1.0, min(1.0, dot))
    return math.acos(dot)


def _l2_normalize(v: NDArray[np.float32]) -> NDArray[np.float32]:
    """Project vector onto the unit hypersphere. Returns v if ||v|| < eps."""
    norm = float(np.linalg.norm(v))
    if norm < _EPS:
        return v
    return v / norm


def compute_sgi(
    question: str,
    context: str,
    response: str,
    *,
    model: str = DEFAULT_MODEL,
    encoder: EmbeddingFn | None = None,
) -> SGIResult:
    """Compute the Semantic Grounding Index for a response.

    Args:
        question: The input query.
        context: Source document, retrieved chunks, or reference text.
        response: The LLM output to evaluate.
        model: Sentence transformer model name. Default ``all-MiniLM-L6-v2``.
        encoder: Optional bring-your-own-embeddings callable taking
            ``list[str]`` and returning an ``(n, d)`` array. Bypasses
            sentence-transformers (no torch required) when provided.

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

    if encoder is not None or model != DEFAULT_MODEL:
        _warn_default_thresholds_with_custom_encoder("compute_sgi", model, encoder is not None)

    embeddings = encode_texts([question, context, response], model_name=model, encoder=encoder)
    q_emb, ctx_emb, resp_emb = embeddings[0], embeddings[1], embeddings[2]

    # L2-normalize to project onto the unit hypersphere (paper Algorithm 1).
    q_hat = _l2_normalize(q_emb)
    c_hat = _l2_normalize(ctx_emb)
    r_hat = _l2_normalize(resp_emb)

    # Angular (geodesic) distances on S^(d-1).
    q_dist = _angular_distance(r_hat, q_hat)
    ctx_dist = _angular_distance(r_hat, c_hat)

    # Degenerate case: response identical to context (theta(r, c) ≈ 0).
    if ctx_dist < _EPS:
        return SGIResult(
            value=10.0,
            normalized=1.0,
            flagged=False,
            q_dist=round(q_dist, 4),
            ctx_dist=round(ctx_dist, 4),
        )

    # Degenerate case: response identical to question (theta(r, q) ≈ 0).
    if q_dist < _EPS:
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

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        encoder: EmbeddingFn | None = None,
    ) -> None:
        """Initialize SGI scorer.

        Args:
            model: Sentence transformer model name or path.
            encoder: Optional bring-your-own-embeddings callable. When set,
                scoring bypasses sentence-transformers (no torch required).
        """
        self.model = model
        self.encoder = encoder

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
            encoder=self.encoder,
        )
