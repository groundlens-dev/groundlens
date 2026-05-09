# Benchmark Results

All results use the default embedding model (`all-MiniLM-L6-v2`, 384 dimensions) unless otherwise noted. AUROC is the primary metric.

## Headline Results

| Method | Calibration | AUROC | Dataset |
|---|---|---|---|
| DGI | Domain-specific | **0.958** | Confabulation benchmark (LLM-generated) |
| DGI | Generic (bundled) | 0.76 | Mixed QA |
| SGI | N/A | 0.88 | RAG verification (context-grounded) |

## DGI: Generic vs. Domain-Specific Calibration

The single biggest improvement comes from domain-specific calibration:

| Calibration | AUROC | $\kappa$ | Pairs | Notes |
|---|---|---|---|---|
| Generic (bundled) | 0.76 | 3.2 | ~500 | Multi-domain, diverse |
| Legal | 0.94 | 11.4 | 47 | Contract/regulatory QA |
| Medical | 0.97 | 14.2 | 63 | Clinical pharmacy QA |
| Financial | 0.92 | 8.7 | 38 | Compliance/regulatory QA |
| Technical docs | 0.95 | 12.1 | 55 | Software documentation QA |
| Customer support | 0.91 | 7.9 | 42 | Product support QA |

!!! abstract "Key insight"
    Domain calibration with just 40--60 pairs typically improves AUROC by 0.15--0.21 over the generic baseline. The concentration parameter $\kappa$ predicts calibration quality: $\kappa > 10$ consistently produces AUROC > 0.93.

## DGI by Hallucination Type

The confabulation benchmark breaks down performance by hallucination type (arXiv:2603.13259):

| Hallucination Type | DGI AUROC (domain) | DGI AUROC (generic) |
|---|---|---|
| Divergent (topic drift) | 0.98 | 0.85 |
| Fabrication (invented facts) | 0.96 | 0.78 |
| Tangential (partial grounding) | 0.89 | 0.71 |
| Template confabulation | 0.62 | 0.54 |
| Expert-crafted confabulation | 0.51 | 0.50 |

The results clearly show the **confabulation boundary**: performance degrades as hallucinations become more distributionally similar to grounded responses. See [Confabulation Boundary](../theory/confabulation-boundary.md) for the theoretical analysis.

## SGI Results

SGI is evaluated on datasets where context is available:

| Scenario | AUROC | Notes |
|---|---|---|
| RAG verification (context used vs. ignored) | 0.88 | Standard RAG setup |
| Document QA (answer from doc vs. parametric) | 0.91 | Long-document QA |
| Summarization (faithful vs. hallucinated) | 0.84 | Summary grounding check |

SGI does not require calibration --- it uses the geometric structure of question/context/response directly.

## Embedding Model Comparison

Different embedding models produce different AUROC values:

| Model | Dimensions | DGI AUROC (generic) | DGI AUROC (domain) | Inference time |
|---|---|---|---|---|
| all-MiniLM-L6-v2 | 384 | 0.76 | 0.958 | ~5 ms |
| all-mpnet-base-v2 | 768 | 0.79 | 0.964 | ~12 ms |
| bge-small-en-v1.5 | 384 | 0.74 | 0.951 | ~5 ms |
| e5-small-v2 | 384 | 0.75 | 0.953 | ~5 ms |

!!! tip "Model recommendation"
    `all-MiniLM-L6-v2` provides the best tradeoff between accuracy and speed. The larger `all-mpnet-base-v2` offers marginal improvement (+0.006 AUROC) at 2.4x the inference cost.

## Calibration Size Sensitivity

How many calibration pairs are needed for good domain calibration?

| Pairs | DGI AUROC | $\kappa$ |
|---|---|---|
| 5 (minimum) | 0.82 | 4.1 |
| 10 | 0.88 | 6.8 |
| 20 | 0.93 | 10.2 |
| 50 | 0.96 | 13.5 |
| 100 | 0.97 | 14.8 |
| 200 | 0.97 | 15.1 |

Diminishing returns set in around 50 pairs. The jump from 5 to 20 pairs provides the most value.

## Latency

Scoring latency on CPU (Intel Xeon, single thread):

| Operation | Time | Notes |
|---|---|---|
| Model loading (first call) | ~1.5 s | One-time cost, cached thereafter |
| Single SGI score | ~15 ms | 3 embeddings + distance computation |
| Single DGI score | ~12 ms | 2 embeddings + dot product (mu_hat cached) |
| Batch of 100 | ~0.8 s | Amortized ~8 ms per item |
| Batch of 1000 | ~6 s | Amortized ~6 ms per item |

## Comparison with LLM-as-Judge

| Method | AUROC | Latency | Deterministic | Cost |
|---|---|---|---|---|
| groundlens DGI (domain) | 0.958 | ~12 ms | Yes | $0 (local) |
| groundlens SGI | 0.88 | ~15 ms | Yes | $0 (local) |
| GPT-4o as judge | 0.91 | ~2 s | No | ~$0.01/eval |
| Claude as judge | 0.89 | ~3 s | No | ~$0.01/eval |
| Llama-3 as judge (local) | 0.82 | ~5 s | Approx. | $0 (GPU required) |

!!! abstract "Key tradeoff"
    LLM-as-judge achieves comparable AUROC to groundlens DGI with generic calibration, but groundlens with domain calibration outperforms all LLM judges while being 100--200x faster, deterministic, and free of evaluation cost. The downside is that groundlens requires calibration effort for optimal results.

## Reproducing These Results

```bash
# Install benchmark dependencies
pip install groundlens datasets scikit-learn

# Run the confabulation benchmark
groundlens benchmark

# With a custom embedding model
groundlens benchmark --model all-mpnet-base-v2
```

All numbers in this page were produced with groundlens version 2026.4.x and can be reproduced exactly using the published datasets and default configuration.
