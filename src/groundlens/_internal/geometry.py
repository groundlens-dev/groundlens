"""Geometric primitives for embedding space operations.

This module provides the mathematical building blocks used by SGI and DGI.
All operations are on vectors in R^n (the embedding space of a sentence
transformer), which can be understood geometrically on the unit hypersphere
S^(n-1) when vectors are L2-normalized.

Key concepts:

- **Euclidean distance** in R^n is used by SGI to compare how far the
  response embedding is from the question vs. the context.

- **Displacement vectors** (r - q) capture the semantic "movement" from
  question to response. DGI projects these onto a reference direction.

- **Unit normalization** maps vectors to S^(n-1). On the unit hypersphere,
  dot product equals cosine similarity, and Euclidean distance is a
  monotonic function of angular distance.

References:
    Marin (2025). Semantic Grounding Index. arXiv:2512.13771.
    Marin (2026). A Geometric Taxonomy of Hallucinations. arXiv:2602.13224.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# Type alias for embedding vectors.
EmbeddingVector = NDArray[np.float32]

# Numerical tolerance for near-zero vectors.
_EPSILON: float = 1e-8


def euclidean_distance(a: EmbeddingVector, b: EmbeddingVector) -> float:
    """Compute Euclidean distance between two embedding vectors.

    Args:
        a: First embedding vector, shape (d,).
        b: Second embedding vector, shape (d,).

    Returns:
        Non-negative scalar distance.
    """
    return float(np.linalg.norm(a - b))


def unit_normalize(v: EmbeddingVector) -> EmbeddingVector:
    """Project vector onto the unit hypersphere S^(n-1).

    Args:
        v: Input vector, shape (d,).

    Returns:
        Unit vector v / ||v||, or the zero vector if ||v|| < epsilon.
    """
    norm = float(np.linalg.norm(v))
    if norm < _EPSILON:
        return v
    return v / norm


def displacement_vector(
    question_emb: EmbeddingVector,
    response_emb: EmbeddingVector,
) -> EmbeddingVector:
    """Compute the displacement from question to response in embedding space.

    The displacement delta = phi(response) - phi(question) captures the
    semantic transformation applied by the LLM when generating a response.
    In grounded responses, this displacement aligns with a characteristic
    reference direction.

    Args:
        question_emb: Question embedding, shape (d,).
        response_emb: Response embedding, shape (d,).

    Returns:
        Displacement vector, shape (d,).
    """
    return response_emb - question_emb


def cosine_similarity(a: EmbeddingVector, b: EmbeddingVector) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector, shape (d,).
        b: Second vector, shape (d,).

    Returns:
        Cosine similarity in [-1, 1]. Returns 0.0 if either vector
        has near-zero norm.
    """
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < _EPSILON or norm_b < _EPSILON:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def mean_direction(vectors: list[EmbeddingVector]) -> EmbeddingVector:
    """Compute the mean direction of a set of unit vectors.

    This is the maximum-likelihood estimate of the mean direction
    parameter mu of a von Mises-Fisher distribution on S^(n-1).

    Args:
        vectors: List of unit-normalized vectors, each shape (d,).

    Returns:
        Unit-normalized mean direction, shape (d,). Zero vector if
        the input vectors cancel out.

    Raises:
        ValueError: If the input list is empty.
    """
    if not vectors:
        msg = "Cannot compute mean direction of empty vector list."
        raise ValueError(msg)

    mu: EmbeddingVector = np.mean(np.stack(vectors), axis=0)
    return unit_normalize(mu)
