# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens", "scikit-learn>=1.3.0"]
# ///
"""Human confabulation benchmark — AUROC evaluation for SGI and DGI.

Loads the cert-framework/human-confabulation-benchmark dataset from
HuggingFace (212 pairs), runs both SGI and DGI scoring on all items,
and reports AUROC using scikit-learn.

Falls back to CSV loading if the HuggingFace ``datasets`` library is
not installed.

Expected dataset columns:
    - question: The input query.
    - response: The LLM output.
    - context: Source text (for SGI evaluation).
    - label: 1 = grounded (factual), 0 = confabulated (hallucination).
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from sklearn.metrics import roc_auc_score

from groundlens.dgi import compute_dgi
from groundlens.sgi import compute_sgi

DATASET_NAME = "cert-framework/human-confabulation-benchmark"
FALLBACK_CSV = Path(__file__).parent / "data" / "confabulation_benchmark.csv"


def load_from_huggingface() -> list[dict[str, str]]:
    """Load benchmark dataset from HuggingFace Hub."""
    from datasets import load_dataset

    ds = load_dataset(DATASET_NAME, split="test")
    return [dict(row) for row in ds]


def load_from_csv(path: Path) -> list[dict[str, str]]:
    """Load benchmark dataset from a local CSV file."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def load_dataset_auto() -> list[dict[str, str]]:
    """Load dataset from HuggingFace, falling back to CSV."""
    try:
        return load_from_huggingface()
    except ImportError:
        print("HuggingFace datasets not installed, trying local CSV...", file=sys.stderr)
        if FALLBACK_CSV.exists():
            return load_from_csv(FALLBACK_CSV)
        print(f"Fallback CSV not found at {FALLBACK_CSV}", file=sys.stderr)
        print("Install datasets: pip install datasets", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error loading from HuggingFace: {exc}", file=sys.stderr)
        if FALLBACK_CSV.exists():
            return load_from_csv(FALLBACK_CSV)
        sys.exit(1)


def run_benchmark(model: str = "all-MiniLM-L6-v2") -> None:
    """Run the full benchmark and print AUROC results."""
    pairs = load_dataset_auto()
    print(f"Loaded {len(pairs)} benchmark items.\n")

    sgi_scores: list[float] = []
    sgi_labels: list[int] = []
    dgi_scores: list[float] = []
    dgi_labels: list[int] = []

    start = time.perf_counter()

    for i, item in enumerate(pairs, 1):
        question = str(item.get("question", ""))
        response = str(item.get("response", ""))
        context = str(item.get("context", ""))
        label = int(item.get("label", 0))

        # SGI requires context.
        if context.strip():
            sgi_result = compute_sgi(
                question=question,
                context=context,
                response=response,
                model=model,
            )
            sgi_scores.append(sgi_result.value)
            sgi_labels.append(label)

        # DGI works without context.
        dgi_result = compute_dgi(
            question=question,
            response=response,
            model=model,
        )
        dgi_scores.append(dgi_result.value)
        dgi_labels.append(label)

        if i % 25 == 0 or i == len(pairs):
            elapsed = time.perf_counter() - start
            rate = i / elapsed if elapsed > 0 else 0
            print(f"\r  Progress: {i}/{len(pairs)} ({rate:.1f} items/s)", end="")

    elapsed = time.perf_counter() - start
    print(f"\n\nCompleted in {elapsed:.1f}s\n")

    # Report results.
    print("=" * 50)
    print("  CONFABULATION BENCHMARK RESULTS")
    print("=" * 50)
    print(f"  Model:     {model}")
    print(f"  Items:     {len(pairs)}")
    print(f"  Time:      {elapsed:.1f}s")
    print("-" * 50)

    if sgi_scores and len(set(sgi_labels)) > 1:
        sgi_auroc = roc_auc_score(sgi_labels, sgi_scores)
        print(f"  SGI AUROC: {sgi_auroc:.4f}  (n={len(sgi_scores)})")
    else:
        print("  SGI AUROC: N/A (insufficient data)")

    if dgi_scores and len(set(dgi_labels)) > 1:
        dgi_auroc = roc_auc_score(dgi_labels, dgi_scores)
        print(f"  DGI AUROC: {dgi_auroc:.4f}  (n={len(dgi_scores)})")
    else:
        print("  DGI AUROC: N/A (insufficient data)")

    print("=" * 50)


if __name__ == "__main__":
    run_benchmark()
