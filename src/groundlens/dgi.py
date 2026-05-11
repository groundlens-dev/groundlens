"""Directional Grounding Index (DGI) — context-free hallucination detection.

DGI evaluates whether an LLM response follows the characteristic semantic
displacement pattern of grounded responses — without requiring source context.
It needs only a question and a response, plus calibration data.

Mathematical formulation:

    delta = phi(response) - phi(question)
    DGI = dot(delta / ||delta||, mu_hat)

where mu_hat is the mean direction of displacement vectors computed from
verified grounded (question, response) pairs.

Geometric interpretation:

    - DGI > 0.3: displacement aligns with grounded reference direction.
    - DGI < 0.3: displacement diverges from grounded patterns.
    - DGI < 0.0: displacement is opposite to grounded direction (high risk).

Calibration:

    DGI accuracy depends heavily on the reference direction mu_hat.
    Generic calibration (bundled dataset) achieves AUROC ~0.76.
    Domain-specific calibration typically reaches AUROC 0.90-0.99.
    The confabulation benchmark reports DGI AUROC 0.958 with domain calibration.

Use cases:

    - Chat/dialogue verification (no retrieval context available).
    - Agent self-verification before returning results.
    - Batch evaluation of LLM outputs at scale.

References:
    Marin (2026). *A Geometric Taxonomy of Hallucinations in LLMs*.
    arXiv:2602.13224v3.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import numpy as np

from groundlens._internal.csv_loader import load_reference_pairs
from groundlens._internal.embeddings import DEFAULT_MODEL, encode_texts
from groundlens._internal.geometry import displacement_vector, unit_normalize
from groundlens._internal.thresholds import DGI_PASS, normalize_dgi
from groundlens.score import DGIResult

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# ── Module-level reference direction cache ───────────────────────────────────

_mu_hat_cache: dict[tuple[str, str], NDArray[np.float32]] = {}


def _compute_reference_direction(
    pairs: list[tuple[str, str]],
    model_name: str = DEFAULT_MODEL,
) -> NDArray[np.float32]:
    """Compute the mean grounded displacement direction (mu_hat).

    Given N verified (question, response) pairs, compute:

        1. Embed all questions and responses.
        2. For each pair, compute delta_i = phi(r_i) - phi(q_i).
        3. Normalize each delta_i to unit length.
        4. Average the unit vectors and re-normalize.

    The result mu_hat is the maximum-likelihood estimate of the mean
    direction of a von Mises-Fisher distribution on S^(n-1).

    Args:
        pairs: List of (question, response) string tuples.
        model_name: Sentence transformer model.

    Returns:
        Unit-normalized mean direction vector, shape ``(d,)``.
    """
    texts: list[str] = []
    for q, r in pairs:
        texts.extend([q, r])

    embeddings = encode_texts(texts, model_name=model_name)

    displacements: list[NDArray[np.float32]] = []
    for i in range(len(pairs)):
        q_emb = embeddings[i * 2]
        r_emb = embeddings[i * 2 + 1]
        delta = displacement_vector(q_emb, r_emb)
        delta_hat = unit_normalize(delta)
        norm = float(np.linalg.norm(delta))
        if norm > 1e-8:
            displacements.append(delta_hat)

    if not displacements:
        msg = "No valid displacement vectors computed from reference pairs."
        raise ValueError(msg)

    mu: NDArray[np.float32] = np.mean(np.stack(displacements), axis=0)
    return unit_normalize(mu)


def _get_mu_hat(
    model_name: str = DEFAULT_MODEL,
    reference_csv: str | None = None,
) -> NDArray[np.float32]:
    """Get the cached reference direction, computing on first access.

    Caches by ``(model_name, reference_csv)`` key. Using different CSV
    paths produces independent reference directions.

    Args:
        model_name: Sentence transformer model.
        reference_csv: Path to user CSV, or ``None`` for bundled data.

    Returns:
        Unit-normalized reference direction, shape ``(d,)``.
    """
    cache_key = (model_name, reference_csv or "__bundled__")

    if cache_key not in _mu_hat_cache:
        logger.info(
            "Computing DGI reference direction (model=%s, data=%s)...",
            model_name,
            reference_csv or "bundled",
        )
        pairs = load_reference_pairs(reference_csv)
        _mu_hat_cache[cache_key] = _compute_reference_direction(pairs, model_name)
        logger.info(
            "DGI reference direction ready (dims=%d, pairs=%d).",
            _mu_hat_cache[cache_key].shape[0],
            len(pairs),
        )

    return _mu_hat_cache[cache_key]


def compute_dgi(
    question: str,
    response: str,
    *,
    model: str = DEFAULT_MODEL,
    reference_csv: str | None = None,
) -> DGIResult:
    """Compute the Directional Grounding Index for a response.

    Args:
        question: The input query.
        response: The LLM output to evaluate.
        model: Sentence transformer model name.
        reference_csv: Path to domain-specific calibration CSV.
            If ``None``, uses the bundled dataset.

    Returns:
        DGIResult with raw score, normalized score, and flag status.

    Raises:
        ValueError: If question or response is empty.

    Example:
        >>> from groundlens import compute_dgi
        >>> result = compute_dgi(
        ...     question="What causes seasons on Earth?",
        ...     response="Seasons are caused by Earth's 23.5-degree axial tilt.",
        ... )
        >>> result.flagged
        False
    """
    if not question.strip():
        msg = "question must be a non-empty string."
        raise ValueError(msg)
    if not response.strip():
        msg = "response must be a non-empty string."
        raise ValueError(msg)

    mu_hat = _get_mu_hat(model, reference_csv)
    embeddings = encode_texts([question, response], model_name=model)
    q_emb, r_emb = embeddings[0], embeddings[1]

    delta = displacement_vector(q_emb, r_emb)
    magnitude = float(np.linalg.norm(delta))

    # Degenerate case: response identical to question.
    if magnitude < 1e-8:
        return DGIResult(value=0.0, normalized=0.0, flagged=True)

    delta_hat = delta / magnitude
    gamma = float(np.dot(delta_hat, mu_hat))

    if math.isnan(gamma):
        logger.warning("DGI produced NaN — check embedding dimensions.")
        return DGIResult(value=0.0, normalized=0.0, flagged=True)

    normalized = round(normalize_dgi(gamma), 4)

    return DGIResult(
        value=round(gamma, 4),
        normalized=normalized,
        flagged=gamma < DGI_PASS,
    )


def reset_calibration_cache() -> None:
    """Clear all cached reference directions. Useful for testing."""
    _mu_hat_cache.clear()


class DGI:
    """Reusable DGI scorer with pre-configured model and calibration.

    Use this class when evaluating multiple responses against the same
    reference direction. Supports both bundled and custom calibration.

    Example:
        >>> dgi = DGI()
        >>> result = dgi.score(
        ...     question="What is ML?",
        ...     response="ML is a branch of AI.",
        ... )
        >>> result.flagged
        False

        >>> dgi = DGI(reference_csv="my_domain_pairs.csv")
        >>> result = dgi.score(question="...", response="...")
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        reference_csv: str | None = None,
    ) -> None:
        """Initialize DGI scorer.

        Args:
            model: Sentence transformer model name.
            reference_csv: Path to domain-specific calibration CSV.
        """
        self.model = model
        self.reference_csv = reference_csv

    def calibrate(
        self,
        pairs: list[tuple[str, str]] | None = None,
        csv_path: str | None = None,
    ) -> None:
        """Set custom calibration data.

        Either provide pairs directly or a path to a CSV file.
        This replaces any previously cached reference direction.

        Args:
            pairs: List of verified (question, response) tuples.
            csv_path: Path to a calibration CSV file.

        Raises:
            ValueError: If neither ``pairs`` nor ``csv_path`` is provided.
        """
        if csv_path is not None:
            self.reference_csv = csv_path
            # Force recomputation on next score() call.
            cache_key = (self.model, csv_path)
            _mu_hat_cache.pop(cache_key, None)
            return

        if pairs is not None:
            # Compute and cache the reference direction directly.
            mu = _compute_reference_direction(pairs, self.model)
            cache_key = (self.model, "__inline__")
            _mu_hat_cache[cache_key] = mu
            self.reference_csv = "__inline__"
            return

        msg = "Provide either 'pairs' or 'csv_path' for calibration."
        raise ValueError(msg)

    def score(self, question: str, response: str) -> DGIResult:
        """Compute DGI for a single response.

        Args:
            question: The input query.
            response: The LLM output to evaluate.

        Returns:
            DGIResult with score and flag status.
        """
        ref = self.reference_csv if self.reference_csv != "__inline__" else None
        if self.reference_csv == "__inline__":
            # Use the inline-calibrated mu_hat.
            cache_key = (self.model, "__inline__")
            if cache_key not in _mu_hat_cache:
                msg = "Call calibrate() before score() when using inline pairs."
                raise RuntimeError(msg)

        return compute_dgi(
            question=question,
            response=response,
            model=self.model,
            reference_csv=ref,
        )
