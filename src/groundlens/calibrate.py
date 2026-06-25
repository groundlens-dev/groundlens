"""Domain-specific calibration for DGI reference direction.

DGI accuracy improves dramatically with domain-specific calibration.
Generic calibration (bundled dataset) achieves AUROC ~0.76.
Domain-specific calibration typically reaches AUROC 0.90-0.99.

This module provides a standalone calibration API for creating,
saving, and loading domain-specific reference directions.

Workflow:
    1. Collect 20-100 verified (question, response) pairs from your domain.
    2. Call ``calibrate()`` to compute the reference direction.
    3. Save the result to JSON for reproducibility.
    4. Pass the CSV path to ``compute_dgi(reference_csv=...)`` or ``DGI(reference_csv=...)``.

Example:
    >>> from groundlens import calibrate
    >>> result = calibrate(pairs=[("Q1?", "A1."), ("Q2?", "A2.")])
    >>> result.auroc_estimate
    0.92
    >>> result.save("my_domain_calibration.json")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from groundlens._internal.embeddings import DEFAULT_MODEL
from groundlens.dgi import _compute_reference_direction

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.typing import NDArray

    from groundlens._internal.embeddings import EmbeddingFn

logger = logging.getLogger(__name__)


@dataclass
class CalibrationResult:
    """Result of DGI calibration.

    Attributes:
        model: Sentence transformer model used for calibration.
        n_pairs: Number of (question, response) pairs used.
        embedding_dim: Dimensionality of the embedding space.
        mu_hat: The computed reference direction vector.
        concentration: Estimated concentration parameter (kappa) of the
            von Mises-Fisher distribution. Higher values indicate more
            consistent displacement directions in the reference data.
    """

    model: str
    n_pairs: int
    embedding_dim: int
    mu_hat: NDArray[np.float32]
    concentration: float
    metadata: dict[str, str] = field(default_factory=dict)

    def save(self, path: str | Path) -> None:
        """Save calibration result to JSON.

        Args:
            path: Output file path. The mu_hat vector is stored as a list.
        """
        data = {
            "model": self.model,
            "n_pairs": self.n_pairs,
            "embedding_dim": self.embedding_dim,
            "mu_hat": self.mu_hat.tolist(),
            "concentration": self.concentration,
            "metadata": self.metadata,
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Calibration saved to %s.", path)

    @classmethod
    def load(cls, path: str | Path) -> CalibrationResult:
        """Load a saved calibration result.

        Args:
            path: Path to JSON calibration file.

        Returns:
            CalibrationResult instance with restored mu_hat vector.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            model=data["model"],
            n_pairs=data["n_pairs"],
            embedding_dim=data["embedding_dim"],
            mu_hat=np.array(data["mu_hat"], dtype=np.float32),
            concentration=data["concentration"],
            metadata=data.get("metadata", {}),
        )


def calibrate(
    pairs: list[tuple[str, str]] | None = None,
    csv_path: str | None = None,
    *,
    model: str = DEFAULT_MODEL,
    encoder: EmbeddingFn | None = None,
    metadata: dict[str, str] | None = None,
) -> CalibrationResult:
    """Compute a DGI reference direction from calibration data.

    Provide either ``pairs`` directly or a ``csv_path`` to a file
    with verified grounded (question, response) pairs.

    Args:
        pairs: List of (question, response) tuples.
        csv_path: Path to a CSV file with ``question`` and ``response`` columns.
        model: Sentence transformer model to use for embedding.
        encoder: Optional bring-your-own-embeddings callable. When set,
            sentence-transformers is bypassed (no torch required).
        metadata: Optional metadata to attach (domain name, date, notes).

    Returns:
        CalibrationResult with computed reference direction and statistics.

    Raises:
        ValueError: If neither ``pairs`` nor ``csv_path`` is provided,
            or if the data contains fewer than 5 pairs.

    Example:
        >>> result = calibrate(pairs=[("Q?", "A.") for _ in range(20)])
        >>> result.n_pairs
        20
    """
    if csv_path is not None:
        from groundlens._internal.csv_loader import load_reference_pairs

        pairs = load_reference_pairs(csv_path)
    elif pairs is None:
        msg = "Provide either 'pairs' or 'csv_path'."
        raise ValueError(msg)

    if len(pairs) < 5:
        msg = (
            f"Calibration requires at least 5 pairs, got {len(pairs)}. "
            "More pairs (20-100) produce better reference directions."
        )
        raise ValueError(msg)

    logger.info("Calibrating DGI with %d pairs using model %s.", len(pairs), model)

    mu_hat = _compute_reference_direction(pairs, model, encoder=encoder)

    # Estimate concentration parameter (kappa) from resultant length.
    # This is a rough estimate — the true MLE for von Mises-Fisher is
    # more complex, but the resultant length R-bar is a sufficient
    # indicator of calibration quality.
    from groundlens._internal.embeddings import encode_texts
    from groundlens._internal.geometry import displacement_vector, unit_normalize

    texts: list[str] = []
    for q, r in pairs:
        texts.extend([q, r])
    embeddings = encode_texts(texts, model_name=model, encoder=encoder)

    unit_displacements = []
    for i in range(len(pairs)):
        delta = displacement_vector(embeddings[i * 2], embeddings[i * 2 + 1])
        norm = float(np.linalg.norm(delta))
        if norm > 1e-8:
            unit_displacements.append(unit_normalize(delta))

    if unit_displacements:
        r_bar = float(np.linalg.norm(np.mean(np.stack(unit_displacements), axis=0)))
    else:
        r_bar = 0.0

    # Approximate kappa from R-bar (Sra, 2012).
    d = mu_hat.shape[0]
    kappa = r_bar * (d - r_bar**2) / (1 - r_bar**2) if r_bar < 0.99 else 100.0

    return CalibrationResult(
        model=model,
        n_pairs=len(pairs),
        embedding_dim=int(mu_hat.shape[0]),
        mu_hat=mu_hat,
        concentration=round(kappa, 2),
        metadata=metadata or {},
    )


@dataclass
class ThresholdFit:
    """Fitted decision thresholds for SGI and DGI on a labeled set.

    Thresholds are chosen by maximizing Youden's J for the rule
    "value >= threshold implies grounded" over the supplied examples.

    Attributes:
        sgi_review: Fitted SGI review threshold, or ``None`` if no contexts
            were supplied (SGI requires context).
        dgi_pass: Fitted DGI pass threshold, or ``None`` if it could not be
            estimated.
        n: Number of examples used for fitting.
        model: Sentence transformer model the scores were computed with.
        metric: Name of the criterion used to pick thresholds.
    """

    sgi_review: float | None
    dgi_pass: float | None
    n: int
    model: str
    metric: str = "youden_j"


def _youden_threshold(
    grounded_vals: list[float],
    hallucinated_vals: list[float],
) -> float:
    """Pick the cutoff ``t`` maximizing Youden's J for "value >= t is grounded".

    J(t) = mean(grounded >= t) + mean(hallucinated < t) - 1, but the constant
    ``-1`` does not affect the argmax, so we maximize the sum of the two
    means. Candidate cutoffs are the sorted unique observed values (plus a
    cutoff just above the maximum). No sklearn required.

    Args:
        grounded_vals: Scores for the grounded (label 0) class.
        hallucinated_vals: Scores for the ungrounded (label 1) class.

    Returns:
        The threshold maximizing Youden's J. Ties resolve to the lowest
        candidate cutoff.
    """
    g = np.asarray(grounded_vals, dtype=np.float64)
    h = np.asarray(hallucinated_vals, dtype=np.float64)
    candidates = np.unique(np.concatenate([g, h]))
    # Also consider a cutoff strictly above the maximum so "flag everything"
    # is reachable when that separates best.
    upper = float(candidates[-1]) + 1.0 if candidates.size else 1.0
    best_t = float(candidates[0]) if candidates.size else 0.0
    best_j = -np.inf
    for t in (*candidates.tolist(), upper):
        tpr = float(np.mean(g >= t)) if g.size else 0.0
        tnr = float(np.mean(h < t)) if h.size else 0.0
        j = tpr + tnr
        if j > best_j:
            best_j = j
            best_t = float(t)
    return best_t


def fit_thresholds(
    examples: list[Mapping[str, object]],
    *,
    model: str = DEFAULT_MODEL,
    encoder: EmbeddingFn | None = None,
    reference_csv: str | None = None,
) -> ThresholdFit:
    """Fit SGI/DGI decision thresholds on a labeled set via Youden's J.

    For each example this computes DGI (and SGI when a ``context`` is
    present), then picks each threshold by maximizing Youden's J for the
    rule "value >= threshold implies grounded".

    Args:
        examples: A list of mappings, each with keys ``question`` (str),
            ``response`` (str), ``label`` (int: ``1`` = ungrounded /
            hallucinated, ``0`` = grounded), and optional ``context`` (str).
        model: Sentence transformer model name.
        encoder: Optional bring-your-own-embeddings callable. Passed through
            to ``compute_dgi`` / ``compute_sgi`` so fitting works without
            torch.
        reference_csv: Optional DGI calibration CSV passed to ``compute_dgi``.

    Returns:
        A :class:`ThresholdFit` with the fitted ``dgi_pass`` and (when any
        contexts were supplied) ``sgi_review`` thresholds.

    Raises:
        ValueError: If ``examples`` is empty, or if both classes (grounded
            and ungrounded) are not present.

    Example:
        >>> fit = fit_thresholds(
        ...     [
        ...         {"question": "Q1?", "response": "A1.", "label": 0},
        ...         {"question": "Q2?", "response": "off-topic", "label": 1},
        ...     ]
        ... )
        >>> fit.metric
        'youden_j'
    """
    from groundlens.dgi import compute_dgi
    from groundlens.sgi import compute_sgi

    if not examples:
        msg = "examples must contain at least one item."
        raise ValueError(msg)

    labels = [int(ex["label"]) for ex in examples]  # type: ignore[call-overload]
    if 0 not in labels or 1 not in labels:
        msg = (
            "fit_thresholds requires both classes present: at least one "
            "grounded (label=0) and one ungrounded (label=1) example."
        )
        raise ValueError(msg)

    dgi_grounded: list[float] = []
    dgi_hallucinated: list[float] = []
    sgi_grounded: list[float] = []
    sgi_hallucinated: list[float] = []

    for ex in examples:
        question = str(ex["question"])
        response = str(ex["response"])
        label = int(ex["label"])  # type: ignore[call-overload]

        dgi = compute_dgi(
            question,
            response,
            model=model,
            reference_csv=reference_csv,
            encoder=encoder,
        )
        (dgi_hallucinated if label == 1 else dgi_grounded).append(dgi.value)

        context = ex.get("context")
        if context:
            sgi = compute_sgi(
                question,
                str(context),
                response,
                model=model,
                encoder=encoder,
            )
            (sgi_hallucinated if label == 1 else sgi_grounded).append(sgi.value)

    dgi_pass: float | None = None
    if dgi_grounded and dgi_hallucinated:
        dgi_pass = _youden_threshold(dgi_grounded, dgi_hallucinated)

    sgi_review: float | None = None
    if sgi_grounded and sgi_hallucinated:
        sgi_review = _youden_threshold(sgi_grounded, sgi_hallucinated)

    return ThresholdFit(
        sgi_review=sgi_review,
        dgi_pass=dgi_pass,
        n=len(examples),
        model=model,
    )
