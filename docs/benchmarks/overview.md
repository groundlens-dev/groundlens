# Benchmarks Overview

groundlens benchmarks measure how well SGI and DGI discriminate between grounded and hallucinated responses. The primary metric is **AUROC** (Area Under the Receiver Operating Characteristic curve), which measures the probability that a randomly chosen grounded response scores higher than a randomly chosen hallucinated response.

## What We Measure

### AUROC (Area Under ROC)

AUROC ranges from 0.0 to 1.0:

| AUROC | Interpretation |
|---|---|
| 1.00 | Perfect discrimination |
| 0.90--0.99 | Excellent --- suitable for production |
| 0.80--0.90 | Good --- useful for triage with some noise |
| 0.70--0.80 | Fair --- informative but not reliable alone |
| 0.50 | Random chance --- no discrimination |

!!! danger "Read this scale against the ceiling of the method"
    For embedding-similarity detectors, an **authorship-controlled** AUROC in the high 0.6s is at the ceiling of what the whole class can do. Nothing in this family lands in the 0.9 band on a controlled evaluation.

    So a reported 0.9+ here is not a signal of quality. It is a signal to go looking for a shortcut: authorship, length, or a generation-condition artifact. We know, because we published one. See [Results](results.md).

### Why AUROC?

AUROC is **threshold-independent**: it evaluates the scoring function's ability to rank grounded responses above hallucinated ones, regardless of where you set the decision threshold. This is important because different deployments may use different thresholds based on their risk tolerance.

## Benchmark Datasets

### Confabulation Benchmark

The primary benchmark dataset, published alongside arXiv:2603.13259. It contains:

- Verified grounded (question, response) pairs
- LLM-generated hallucinations (produced by instructing models to answer without access to correct information)
- Template-based confabulations (factual substitutions in correct response templates)
- Context-annotated examples (for SGI evaluation)

**Dataset**: `cert-framework/human-confabulation-benchmark` on HuggingFace.

### Domain-Specific Benchmarks

Additional benchmark datasets for specific verticals:

| Domain | Pairs | Grounded | Hallucinated | Available |
|---|---|---|---|---|
| General | 200 | 100 | 100 | Bundled |
| Legal | 150 | 75 | 75 | On request |
| Medical | 180 | 90 | 90 | On request |
| Financial | 120 | 60 | 60 | On request |

## How to Run Benchmarks

### CLI

```bash
# Default benchmark (confabulation benchmark)
groundlens benchmark

# Custom dataset
groundlens benchmark --dataset cert-framework/human-confabulation-benchmark

# Custom model
groundlens benchmark --model all-mpnet-base-v2
```

### Python API

```python
from groundlens import compute_sgi, compute_dgi
from sklearn.metrics import roc_auc_score

# Load your benchmark dataset
dataset = load_benchmark()  # Your loading logic

sgi_scores, sgi_labels = [], []
dgi_scores, dgi_labels = [], []

for item in dataset:
    question = item["question"]
    response = item["response"]
    context = item.get("context")
    label = item["label"]  # 1 = grounded, 0 = hallucinated

    # SGI (when context is available)
    if context:
        sgi_result = compute_sgi(question=question, context=context, response=response)
        sgi_scores.append(sgi_result.value)
        sgi_labels.append(label)

    # DGI (always)
    dgi_result = compute_dgi(question=question, response=response)
    dgi_scores.append(dgi_result.value)
    dgi_labels.append(label)

# Compute AUROC
print(f"SGI AUROC: {roc_auc_score(sgi_labels, sgi_scores):.4f}")
print(f"DGI AUROC: {roc_auc_score(dgi_labels, dgi_scores):.4f}")
```

### Requirements

```bash
pip install datasets scikit-learn  # Required for benchmark command
```

## Evaluation Protocol

To ensure fair comparison, all benchmarks follow the same protocol:

1. **Fixed embedding model**: Default `all-MiniLM-L6-v2` unless stated otherwise.
2. **No threshold tuning on test data**: Thresholds are fixed before evaluation.
3. **Separate calibration and test sets**: For DGI, calibration pairs are never in the test set.
4. **Stratified evaluation**: AUROC is computed separately for each hallucination type (divergent, tangential, confabulation).

The first four are table stakes. The next four are the ones that decide whether a number means anything, and most published detectors, including our own earlier work, fail them.

5. **Authorship control.** The grounded and the confabulated text must come from the same author. If the true answers are machine-written and the false ones human-written (or the reverse), the label is correlated with authorship and a detector can score highly by recognising **who wrote the text** rather than whether it is grounded. A detector that loses its score under this control was reading authorship. Ours did: a logistic probe falls 0.932 → 0.660, an MLP 0.935 → 0.675, the directional score to 0.606.
6. **Length matching.** Report the length-matched AUROC next to the raw one. RAGTruth-QA is the cautionary case: an apparent 0.705 falls to 0.634 once lengths are matched.
7. **Register binning.** Report the per-bin curve from out-of-register to in-register, not a single pooled AUROC. Pooling hides the wall, which is the entire phenomenon.
8. **Publish the blind spot as a number**, not as a caveat at the bottom of the page.

!!! danger "House rule"
    **No benchmark number ships without the authorship and length controls.** If a figure has not been through them, label it *pending controls* or do not publish it. This applies to this documentation, the README, the papers and the slides.

## Reproducing Results

All reported results can be reproduced exactly because:

- groundlens scoring is **deterministic** (no sampling)
- Benchmark datasets are **versioned** and publicly available
- The embedding model is **fixed** and downloadable

!!! warning "Determinism is not validity"
    Reproducing a number guarantees you get the same number twice. It does not guarantee the number measures grounding. An authorship artifact reproduces perfectly. That is what the controls above are for.

```bash
groundlens benchmark --dataset cert-framework/human-confabulation-benchmark
```

This dataset has a known authorship confound (grounded answers written by a model, confabulations written by a person). The benchmark prints a warning above its AUROC. Read it before quoting anything.

See [Results](results.md) for the full numbers.
