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

## Reproducing Results

All reported results can be reproduced exactly because:

- groundlens scoring is **deterministic** (no sampling)
- Benchmark datasets are **versioned** and publicly available
- The embedding model is **fixed** and downloadable

```bash
# Reproduce the headline DGI AUROC 0.958 result
groundlens benchmark --dataset cert-framework/human-confabulation-benchmark
```

See [Results](results.md) for the full numbers.
