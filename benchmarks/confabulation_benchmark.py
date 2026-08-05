# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens[benchmark]"]
# ///
"""Human confabulation benchmark — AUROC evaluation for SGI and DGI.

WARNING: this dataset has an authorship confound. Every grounded response
was written by a model from a source; every confabulation was written by a
person from memory. Authorship is perfectly correlated with the label, so a
detector can score highly here by recognising who wrote the text rather than
whether it is grounded. Hold authorship constant and a logistic probe falls
from 0.932 to 0.660, an MLP from 0.935 to 0.675, and the directional score
to 0.606.

The AUROC this script prints is an upper bound contaminated by authorship.
Do not publish it. See *The Register Wall* for the controlled evaluation.

Loads the cert-framework/human-confabulation-benchmark dataset from
HuggingFace (212 pairs), runs both SGI and DGI scoring on all items,
and reports AUROC using scikit-learn.

Falls back to a local CSV if the HuggingFace ``datasets`` library is not
installed or the Hub is unreachable. The fallback ships in the repo at
``benchmarks/data/confabulation_benchmark.csv``, derived from the bundled
reference set, so the weekly job produces a result even with no network.

Writes a JSON result file to ``--output`` (default ``benchmarks/results``) so
the run has an artifact to upload.

Expected dataset columns:
    - question: The input query.
    - response: The LLM output.
    - context: Source text (for SGI evaluation).
    - label: 1 = grounded (factual), 0 = confabulated.
    NOTE: this is the OPPOSITE of the polarity groundlens.fit_thresholds()
    expects (1 = ungrounded). Flip the column before feeding this file to
    fit_thresholds, or you will silently fit inverted thresholds. (hallucination).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sklearn.metrics import roc_auc_score

from groundlens._internal.embeddings import DEFAULT_MODEL
from groundlens._version import __version__
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


def expand_pairs(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Turn one row carrying both classes into two labelled items.

    The dataset ships as ``id, domain, question, grounded_response,
    fabricated_response`` - one row is a matched pair, not a single judgeable
    item. This benchmark was written against a flat ``question, response,
    context, label`` schema that has never existed in the file, so every
    ``item["response"]`` came back empty and the first call raised
    ``ValueError: response must be a non-empty string``.

    Note what is NOT here: a context column. This dataset carries no source
    text, so SGI cannot be computed on it at all. Only DGI can.
    """
    out: list[dict[str, str]] = []
    skipped = 0
    for row in rows:
        question = str(row.get("question", "") or "").strip()
        grounded = str(row.get("grounded_response", "") or "").strip()
        fabricated = str(row.get("fabricated_response", "") or "").strip()
        if not (question and grounded and fabricated):
            skipped += 1
            continue
        domain = str(row.get("domain", "") or "unknown")
        item_id = str(row.get("id", "") or "")
        for response, label in ((grounded, 1), (fabricated, 0)):
            out.append(
                {
                    "id": item_id,
                    "domain": domain,
                    "question": question,
                    "response": response,
                    "context": "",
                    "label": str(label),
                }
            )
    if skipped:
        print(f"  skipped {skipped} incomplete rows", file=sys.stderr)
    return out


def run_benchmark(model: str = DEFAULT_MODEL, output_dir: Path | None = None) -> None:
    """Run the full benchmark and print AUROC results."""
    rows = load_dataset_auto()
    pairs = expand_pairs(rows)
    print(
        f"Loaded {len(rows)} rows -> {len(pairs)} scored items "
        f"({sum(1 for p in pairs if p['label'] == '1')} grounded / "
        f"{sum(1 for p in pairs if p['label'] == '0')} fabricated)."
    )

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

    sgi_auroc: float | None = None
    if sgi_scores and len(set(sgi_labels)) > 1:
        sgi_auroc = float(roc_auc_score(sgi_labels, sgi_scores))
        print(f"  SGI AUROC: {sgi_auroc:.4f}  (n={len(sgi_scores)})")
    else:
        print(
            "  SGI AUROC: not computable - this dataset carries no "
            "source text, so there is no context to score against. "
            "DGI only."
        )

    dgi_auroc: float | None = None
    if dgi_scores and len(set(dgi_labels)) > 1:
        dgi_auroc = float(roc_auc_score(dgi_labels, dgi_scores))
        print(f"  DGI AUROC: {dgi_auroc:.4f}  (n={len(dgi_scores)})")
    else:
        print("  DGI AUROC: N/A (insufficient data)")

    print("=" * 50)

    # Write the artifact. The workflow uploads benchmarks/results/, which never
    # existed because nothing here ever wrote to it.
    out = output_dir or Path(__file__).parent / "results"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "timestamp_utc": stamp,
        "groundlens_version": __version__,
        "encoder": model,
        "n_items": len(pairs),
        "elapsed_seconds": round(elapsed, 2),
        "sgi_auroc": sgi_auroc,
        "sgi_n": len(sgi_scores),
        "dgi_auroc": dgi_auroc,
        "dgi_n": len(dgi_scores),
        "warning": (
            "Authorship confound: every grounded response was written by a model "
            "from a source and every confabulation by a person from memory, so "
            "authorship is perfectly correlated with the label. These AUROCs are "
            "an upper bound. Do not publish them."
        ),
    }
    result_path = out / f"confabulation_benchmark_{stamp}.json"
    result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (out / "latest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"  Results written to {result_path}")


def main() -> None:
    """Parse arguments and run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Sentence transformer model (default: the calibrated default encoder).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "results",
        help="Directory for the JSON result file.",
    )
    args = parser.parse_args()
    run_benchmark(model=args.model, output_dir=args.output)


if __name__ == "__main__":
    main()
