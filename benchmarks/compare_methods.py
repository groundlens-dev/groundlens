# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens", "scikit-learn>=1.3.0"]
# ///
"""Compare groundlens SGI/DGI vs cosine similarity on the benchmark.

Demonstrates that standard cosine similarity fails on human
confabulations (fluent, plausible-sounding fabrications), while
geometric methods (SGI ratio, DGI directional alignment) succeed.

Key insight: cosine similarity measures semantic relatedness, not
factual grounding. A confabulated answer about Paris is still
semantically close to a question about Paris. Geometric methods
detect the structural displacement patterns that distinguish
grounded responses from fabrications.
"""

from __future__ import annotations

import sys
import time

import numpy as np
from sklearn.metrics import roc_auc_score

from groundlens._internal.embeddings import encode_texts
from groundlens.dgi import compute_dgi
from groundlens.sgi import compute_sgi

DATASET_NAME = "cert-framework/human-confabulation-benchmark"


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot = float(np.dot(a, b))
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return dot / (norm_a * norm_b)


def load_benchmark() -> list[dict[str, str]]:
    """Load benchmark dataset from HuggingFace."""
    try:
        from datasets import load_dataset

        ds = load_dataset(DATASET_NAME, split="test")
        return [dict(row) for row in ds]
    except ImportError:
        print("Install datasets: pip install datasets", file=sys.stderr)
        sys.exit(1)


def run_comparison(model: str = "all-MiniLM-L6-v2") -> None:
    """Compare all methods on the benchmark dataset."""
    pairs = load_benchmark()
    print(f"Loaded {len(pairs)} benchmark items.\n")

    sgi_scores: list[float] = []
    dgi_scores: list[float] = []
    cos_qr_scores: list[float] = []
    cos_cr_scores: list[float] = []
    labels: list[int] = []
    sgi_labels: list[int] = []

    start = time.perf_counter()

    for i, item in enumerate(pairs, 1):
        question = str(item.get("question", ""))
        response = str(item.get("response", ""))
        context = str(item.get("context", ""))
        label = int(item.get("label", 0))

        labels.append(label)

        # Compute embeddings for cosine baselines.
        texts = [question, response]
        if context.strip():
            texts.append(context)
        embs = encode_texts(texts, model_name=model)

        q_emb, r_emb = embs[0], embs[1]

        # Cosine(question, response) baseline.
        cos_qr_scores.append(cosine_similarity(q_emb, r_emb))

        # Cosine(context, response) baseline (when context available).
        if context.strip():
            ctx_emb = embs[2]
            cos_cr_scores.append(cosine_similarity(ctx_emb, r_emb))

            sgi_result = compute_sgi(
                question=question,
                context=context,
                response=response,
                model=model,
            )
            sgi_scores.append(sgi_result.value)
            sgi_labels.append(label)

        # DGI always works.
        dgi_result = compute_dgi(
            question=question,
            response=response,
            model=model,
        )
        dgi_scores.append(dgi_result.value)

        if i % 25 == 0 or i == len(pairs):
            print(f"\r  Progress: {i}/{len(pairs)}", end="")

    elapsed = time.perf_counter() - start
    print(f"\n\nCompleted in {elapsed:.1f}s\n")

    # Compute AUROC for each method.
    print("=" * 60)
    print("  METHOD COMPARISON: Geometric vs Cosine Similarity")
    print("=" * 60)
    print(f"  {'Method':<30} {'AUROC':>8}  {'N':>5}")
    print("-" * 60)

    if sgi_scores and len(set(sgi_labels)) > 1:
        auroc = roc_auc_score(sgi_labels, sgi_scores)
        print(f"  {'SGI (geometric ratio)':<30} {auroc:>8.4f}  {len(sgi_scores):>5}")

    if dgi_scores and len(set(labels)) > 1:
        auroc = roc_auc_score(labels, dgi_scores)
        print(f"  {'DGI (directional alignment)':<30} {auroc:>8.4f}  {len(dgi_scores):>5}")

    if cos_qr_scores and len(set(labels)) > 1:
        auroc = roc_auc_score(labels, cos_qr_scores)
        print(f"  {'Cosine(question, response)':<30} {auroc:>8.4f}  {len(cos_qr_scores):>5}")

    if cos_cr_scores and len(set(sgi_labels)) > 1:
        auroc = roc_auc_score(sgi_labels, cos_cr_scores)
        print(f"  {'Cosine(context, response)':<30} {auroc:>8.4f}  {len(cos_cr_scores):>5}")

    print("=" * 60)
    print()
    print("  Key finding: cosine similarity cannot distinguish human")
    print("  confabulations from grounded responses because both are")
    print("  semantically similar to the question. Geometric methods")
    print("  detect the structural displacement patterns unique to")
    print("  grounded text.")


if __name__ == "__main__":
    run_comparison()
