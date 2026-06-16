"""CSV loading for DGI reference pairs and evaluation datasets.

Two sources of reference pairs:

1. **Bundled dataset**: Ships with groundlens in ``groundlens/data/reference_pairs.csv``.
   Contains verified grounded (question, response) pairs across finance,
   medical, science, and history domains. Used when no user CSV is provided.

2. **User-provided CSV**: Domain-specific pairs that improve DGI accuracy.
   Generic calibration (bundled) achieves AUROC ~0.76.
   Domain-specific calibration typically reaches AUROC 0.90-0.99.

User CSV format:
    - Comma or semicolon delimited (auto-detected from first 1024 bytes).
    - Required columns: ``question`` and one of ``response``, ``answer``, or ``output``.
    - Header row required. UTF-8 encoding.
    - Each row must be a **verified grounded** (question, response) pair.
      Do NOT include hallucinated responses — they degrade calibration.
"""

from __future__ import annotations

import csv
import logging
from importlib import resources
from pathlib import Path

logger = logging.getLogger(__name__)


def load_reference_pairs(
    reference_csv: str | None = None,
) -> list[tuple[str, str]]:
    """Load grounded (question, response) pairs for DGI calibration.

    Args:
        reference_csv: Path to a user-provided CSV file. If ``None``,
            loads the bundled dataset.

    Returns:
        List of ``(question, response)`` string tuples.

    Raises:
        FileNotFoundError: If ``reference_csv`` path does not exist.
        ValueError: If the CSV is missing required columns or has no valid rows.
    """
    if reference_csv is not None:
        return _load_user_csv(reference_csv)
    return _load_bundled_csv()


def _load_bundled_csv() -> list[tuple[str, str]]:
    """Load the bundled reference dataset from package data.

    Auto-detects the delimiter (comma or semicolon) from the file header
    so the loader is robust to dataset format changes between releases.
    """
    pairs: list[tuple[str, str]] = []

    ref = resources.files("groundlens.data").joinpath("reference_pairs.csv")
    raw = ref.read_text(encoding="utf-8-sig")

    # Auto-detect delimiter from the first 1024 chars (same heuristic as user loader).
    sample = raw[:1024]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","

    reader = csv.DictReader(raw.splitlines(), delimiter=delimiter)

    for row in reader:
        q = row.get("question", "").strip()
        ans = row.get("grounded_response", "").strip()
        if q and ans:
            pairs.append((q, ans))

    if not pairs:
        msg = (
            "Bundled reference dataset loaded 0 pairs. The package installation may be corrupted."
        )
        raise ValueError(msg)

    logger.info("Loaded %d bundled reference pairs.", len(pairs))
    return pairs


def _load_user_csv(path: str) -> list[tuple[str, str]]:
    """Load user-provided reference CSV with auto-detected delimiter."""
    p = Path(path)

    if not p.exists():
        msg = (
            f"Reference CSV not found: {path}\n"
            "Provide a path to a CSV with columns: question, response"
        )
        raise FileNotFoundError(msg)

    # Auto-detect delimiter from first line.
    with p.open(encoding="utf-8") as f:
        sample = f.read(1024)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","

    pairs: list[tuple[str, str]] = []

    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        fieldnames = reader.fieldnames or []

        if "question" not in fieldnames:
            msg = f"CSV missing required 'question' column. Found columns: {fieldnames}"
            raise ValueError(msg)

        # Accept multiple response column names.
        response_col: str | None = None
        for candidate in ("response", "answer", "output", "grounded_response"):
            if candidate in fieldnames:
                response_col = candidate
                break

        if response_col is None:
            msg = (
                f"CSV missing response column. "
                f"Expected one of: 'response', 'answer', 'output'. "
                f"Found columns: {fieldnames}"
            )
            raise ValueError(msg)

        for row in reader:
            q = row.get("question", "").strip()
            ans = row.get(response_col, "").strip()
            if q and ans:
                pairs.append((q, ans))

    if not pairs:
        msg = (
            f"No valid pairs loaded from {path}. "
            "Check that question and response columns contain data."
        )
        raise ValueError(msg)

    logger.info("Loaded %d reference pairs from %s.", len(pairs), path)
    return pairs
