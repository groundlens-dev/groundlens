"""Loader for the bundled certified DGI reference direction (``mu_hat``).

The default DGI reference direction is precomputed and shipped as
``groundlens/data/generic_reference.json`` so scoring does not re-embed the
calibration corpus at runtime. The vector lives in the embedding space of a
specific encoder (:attr:`CertifiedReference.embedding_model`) and is only valid
for that encoder; any other encoder must recompute its own direction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

_REFERENCE_FILE = "generic_reference.json"


@dataclass(frozen=True)
class CertifiedReference:
    """The bundled, precomputed DGI reference for the default encoder."""

    mu_hat: NDArray[np.float32]
    embedding_model: str
    embedding_dimensions: int
    optimal_threshold: float


@lru_cache(maxsize=1)
def load_certified_reference() -> CertifiedReference:
    """Load and cache the bundled certified DGI reference direction."""
    raw = resources.files("groundlens.data").joinpath(_REFERENCE_FILE).read_text(encoding="utf-8")
    data = json.loads(raw)
    stats = data["statistics"]
    mu = np.asarray(data["mean_direction"], dtype=np.float32)
    norm = float(np.linalg.norm(mu))
    if norm > 0.0:
        mu = (mu / norm).astype(np.float32)  # exact unit, matching the recomputed path
    mu.setflags(write=False)  # cached and shared; must not be mutated by callers
    return CertifiedReference(
        mu_hat=mu,
        embedding_model=str(stats["embedding_model"]),
        embedding_dimensions=int(stats["embedding_dimensions"]),
        optimal_threshold=float(stats["optimal_threshold"]),
    )
