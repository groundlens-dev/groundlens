"""Bundled data files for groundlens calibration and benchmarking.

Public helpers expose the on-disk locations of the bundled CSVs so a
deployment can load them with :func:`groundlens.compute_dgi` via the
``reference_csv=`` argument without hard-coding paths.

Available datasets:

- ``reference_pairs_path()`` — the general bundled calibration corpus
  spanning finance / medical / science / history. Used by default when
  no domain-specific calibration is provided.
- ``banking_reference_pairs_path()`` — banking-domain corpus covering
  credit, AML, KYC, fraud, sanctions, concentration, and model risk
  governance. Recommended starting point for regulated banking
  deployments.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

__all__ = [
    "banking_reference_pairs_path",
    "reference_pairs_path",
]


def reference_pairs_path() -> Path:
    """Return the path to the bundled general-domain reference pairs CSV."""
    ref = resources.files("groundlens.data").joinpath("reference_pairs.csv")
    return Path(str(ref))


def banking_reference_pairs_path() -> Path:
    """Return the path to the bundled banking-domain reference pairs CSV.

    The CSV covers seven banking sub-domains (credit, AML, KYC, fraud,
    sanctions, concentration, model risk) with 25 verified
    (question, grounded_response, fabricated_response) triples. Use as
    a starting point for DGI calibration in regulated banking
    deployments; expect AUROC ~0.85+ with this corpus alone, and
    AUROC > 0.95 with deployment-specific extensions to 100-200 pairs.
    """
    ref = resources.files("groundlens.data").joinpath("banking_reference_pairs.csv")
    return Path(str(ref))
