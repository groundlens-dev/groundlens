"""Groundlens CLI — hallucination detection from the command line.

Provides subcommands for single-response checking, batch CSV evaluation,
DGI calibration, and benchmark execution. All imports of scoring functions
are deferred to keep ``--help`` fast.

Usage::

    groundlens check --question "What is X?" --response "X is Y." --context "Source."
    groundlens evaluate input.csv --output results.csv
    groundlens calibrate --pairs domain_pairs.csv --output calibration.json
    groundlens benchmark
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def _cmd_check(args: argparse.Namespace) -> None:
    """Handle the ``check`` subcommand."""
    from groundlens.evaluate import evaluate

    score = evaluate(
        question=args.question,
        response=args.response,
        context=args.context,
        model=args.model,
    )

    print(f"Method:      {score.method}")
    print(f"Score:       {score.value:.4f}")
    print(f"Normalized:  {score.normalized:.4f}")
    print(f"Flagged:     {score.flagged}")
    print(f"Explanation: {score.explanation}")


def _cmd_evaluate(args: argparse.Namespace) -> None:
    """Handle the ``evaluate`` subcommand."""
    from groundlens.evaluate import evaluate

    input_path = Path(args.input_csv)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    rows: list[dict[str, str]] = []
    with input_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)

    if not rows:
        print("Error: input CSV is empty.", file=sys.stderr)
        sys.exit(1)

    results: list[dict[str, str]] = []
    total = len(rows)

    for i, row in enumerate(rows, 1):
        question = row.get("question", "")
        response = row.get("response", "")
        context = row.get("context")

        if not question or not response:
            print(
                f"Warning: row {i} missing question or response, skipping.",
                file=sys.stderr,
            )
            continue

        score = evaluate(
            question=question,
            response=response,
            context=context if context and context.strip() else None,
            model=args.model,
            reference_csv=args.reference_csv,
        )

        out_row = {
            **row,
            "groundlens_method": score.method,
            "groundlens_score": f"{score.value:.4f}",
            "groundlens_normalized": f"{score.normalized:.4f}",
            "groundlens_flagged": str(score.flagged),
            "groundlens_explanation": score.explanation,
        }
        results.append(out_row)

        print(f"\r  Evaluated {i}/{total}", end="", file=sys.stderr)

    print(file=sys.stderr)

    if not results:
        print("Error: no valid rows to write.", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    fieldnames = list(results[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    flagged_count = sum(1 for r in results if r["groundlens_flagged"] == "True")
    print(f"Wrote {len(results)} results to {output_path}")
    print(f"  Flagged: {flagged_count}/{len(results)}")


def _cmd_calibrate(args: argparse.Namespace) -> None:
    """Handle the ``calibrate`` subcommand."""
    from groundlens.calibrate import calibrate

    pairs_path = Path(args.pairs)
    if not pairs_path.exists():
        print(f"Error: pairs file not found: {pairs_path}", file=sys.stderr)
        sys.exit(1)

    result = calibrate(csv_path=str(pairs_path), model=args.model)

    output_path = Path(args.output)
    result.save(output_path)

    print("Calibration complete.")
    print(f"  Pairs:         {result.n_pairs}")
    print(f"  Embedding dim: {result.embedding_dim}")
    print(f"  Concentration: {result.concentration:.2f}")
    print(f"  Saved to:      {output_path}")


def _cmd_benchmark(args: argparse.Namespace) -> None:
    """Handle the ``benchmark`` subcommand."""
    from groundlens.dgi import compute_dgi
    from groundlens.sgi import compute_sgi

    dataset_name = args.dataset

    # Try loading from HuggingFace datasets first.
    pairs: list[dict[str, str]] = []
    try:
        from datasets import load_dataset

        print(f"Loading dataset: {dataset_name}")
        ds = load_dataset(dataset_name, split="test")
        for row in ds:
            pairs.append(dict(row))
    except ImportError:
        print(
            "HuggingFace 'datasets' not installed. Install with: pip install datasets",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"Error loading dataset: {exc}", file=sys.stderr)
        sys.exit(1)

    if not pairs:
        print("Error: dataset is empty.", file=sys.stderr)
        sys.exit(1)

    print(f"Running benchmark on {len(pairs)} items...")

    sgi_scores: list[float] = []
    sgi_labels: list[int] = []
    dgi_scores: list[float] = []
    dgi_labels: list[int] = []

    for i, item in enumerate(pairs, 1):
        question = item.get("question", "")
        response = item.get("response", "")
        context = item.get("context", "")
        label = int(item.get("label", 0))

        if context and context.strip():
            sgi_result = compute_sgi(
                question=question,
                context=context,
                response=response,
                model=args.model,
            )
            sgi_scores.append(sgi_result.value)
            sgi_labels.append(label)

        dgi_result = compute_dgi(
            question=question,
            response=response,
            model=args.model,
        )
        dgi_scores.append(dgi_result.value)
        dgi_labels.append(label)

        if i % 20 == 0 or i == len(pairs):
            print(f"\r  Processed {i}/{len(pairs)}", end="", file=sys.stderr)

    print(file=sys.stderr)

    # Compute AUROC if sklearn is available.
    try:
        from sklearn.metrics import roc_auc_score

        print("\n--- Benchmark Results ---")
        if sgi_scores:
            sgi_auroc = roc_auc_score(sgi_labels, sgi_scores)
            print(f"SGI AUROC: {sgi_auroc:.4f} (n={len(sgi_scores)})")
        if dgi_scores:
            dgi_auroc = roc_auc_score(dgi_labels, dgi_scores)
            print(f"DGI AUROC: {dgi_auroc:.4f} (n={len(dgi_scores)})")
    except ImportError:
        print(
            "\nscikit-learn not installed — cannot compute AUROC.",
            file=sys.stderr,
        )
        print(f"SGI evaluations: {len(sgi_scores)}")
        print(f"DGI evaluations: {len(dgi_scores)}")


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the groundlens CLI."""
    from groundlens._version import __version__

    parser = argparse.ArgumentParser(
        prog="groundlens",
        description="Geometric LLM hallucination detection. No second LLM. Deterministic.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"groundlens {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── check ──────────────────────────────────────────────────────────────
    check_parser = subparsers.add_parser(
        "check",
        help="Evaluate a single response for hallucination risk.",
    )
    check_parser.add_argument("--question", required=True, help="The input question.")
    check_parser.add_argument("--response", required=True, help="The LLM response to evaluate.")
    check_parser.add_argument("--context", default=None, help="Source context (enables SGI).")
    check_parser.add_argument(
        "--model", default="all-MiniLM-L6-v2", help="Sentence transformer model."
    )

    # ── evaluate ───────────────────────────────────────────────────────────
    eval_parser = subparsers.add_parser(
        "evaluate",
        help="Batch evaluate a CSV of question/response pairs.",
    )
    eval_parser.add_argument("input_csv", help="Input CSV with question,response[,context].")
    eval_parser.add_argument("--output", required=True, help="Output CSV path.")
    eval_parser.add_argument(
        "--model", default="all-MiniLM-L6-v2", help="Sentence transformer model."
    )
    eval_parser.add_argument("--reference-csv", default=None, help="DGI calibration CSV path.")

    # ── calibrate ──────────────────────────────────────────────────────────
    cal_parser = subparsers.add_parser(
        "calibrate",
        help="Compute DGI reference direction from calibration pairs.",
    )
    cal_parser.add_argument("--pairs", required=True, help="CSV with question,response columns.")
    cal_parser.add_argument(
        "--output", required=True, help="Output JSON path for calibration data."
    )
    cal_parser.add_argument(
        "--model", default="all-MiniLM-L6-v2", help="Sentence transformer model."
    )

    # ── benchmark ──────────────────────────────────────────────────────────
    bench_parser = subparsers.add_parser(
        "benchmark",
        help="Run the confabulation benchmark.",
    )
    bench_parser.add_argument(
        "--dataset",
        default="cert-framework/human-confabulation-benchmark",
        help="HuggingFace dataset name.",
    )
    bench_parser.add_argument(
        "--model", default="all-MiniLM-L6-v2", help="Sentence transformer model."
    )

    return parser


def main() -> None:
    """Entry point for the groundlens CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    handlers = {
        "check": _cmd_check,
        "evaluate": _cmd_evaluate,
        "calibrate": _cmd_calibrate,
        "benchmark": _cmd_benchmark,
    }

    handler = handlers.get(args.command)
    if handler is not None:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
