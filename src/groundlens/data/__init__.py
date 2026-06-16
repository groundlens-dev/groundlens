"""Bundled data files for groundlens calibration and benchmarking.

Public helpers expose the on-disk location of the bundled CSV so a
deployment can load it with :func:`groundlens.compute_dgi` via the
``reference_csv=`` argument without hard-coding paths.

Available dataset:

- ``reference_pairs_path()`` — the bundled cross-domain calibration
  corpus (212 ``(question, grounded_response, fabricated_response)``
  triples across python_coding, finance, medical, science,
  typescript_coding, history, law, general, geography). Sourced from
  the open ``groundlens-dev/grounding-benchmark`` repository
  (CC BY 4.0). Used by default when no domain-specific calibration is
  provided.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

__all__ = [
    "reference_pairs_path",
]


def reference_pairs_path() -> Path:
    """Return the path to the bundled reference pairs CSV."""
    ref = resources.files("groundlens.data").joinpath("reference_pairs.csv")
    return Path(str(ref))
