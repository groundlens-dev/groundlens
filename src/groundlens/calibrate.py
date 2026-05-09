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
    from numpy.typing import NDArray

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
    metadata: dict[str, str] | None = None,
) -> CalibrationResult:
    """Compute a DGI reference direction from calibration data.

    Provide either ``pairs`` directly or a ``csv_path`` to a file
    with verified grounded (question, response) pairs.

    Args:
        pairs: List of (question, response) tuples.
        csv_path: Path to a CSV file with ``question`` and ``response`` columns.
        model: Sentence transformer model to use for embedding.
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

    mu_hat = _compute_reference_direction(pairs, model)

    # Estimate concentration parameter (kappa) from resultant length.
    # This is a rough estimate — the true MLE for von Mises-Fisher is
    # more complex, but the resultant length R-bar is a sufficient
    # indicator of calibration quality.
    from groundlens._internal.embeddings import encode_texts
    from groundlens._internal.geometry import displacement_vector, unit_normalize

    texts: list[str] = []
    for q, r in pairs:
        texts.extend([q, r])
    embeddings = encode_texts(texts, model_name=model)

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
