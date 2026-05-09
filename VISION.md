# Vision -- Geometric methods for LLM reliability

## The problem

LLM hallucination detection is stuck in a paradox: the dominant approach uses a second LLM to judge the first. This creates three fundamental issues:

1. **Non-determinism.** Ask the judge LLM the same question twice and you may get different verdicts. You cannot reproduce results, you cannot audit decisions, and you cannot explain to a regulator why a specific output was flagged or passed.

2. **Circular trust.** If you do not trust LLM A's output, why would you trust LLM B's judgment of that output? Both models share the same failure modes -- they confabulate, they are sensitive to phrasing, and their confidence is poorly calibrated.

3. **Cost and latency.** Running a second LLM doubles your inference cost and adds a serial dependency to every request. At scale, this is a tax on every token your system produces.

Probabilistic sampling methods (self-consistency, token-level entropy) improve on the second-LLM approach but remain non-deterministic. They require multiple forward passes and produce scores that shift between runs.

## The groundlens approach

groundlens takes a different path: use the geometry of embedding spaces to detect hallucinations deterministically.

The core insight is that when an LLM engages with source material, the spatial relationships between question, context, and response embeddings follow predictable geometric patterns. When the LLM confabulates, those patterns break.

### SGI -- Semantic Grounding Index

SGI measures whether a response moved toward the provided context or stayed near the question in embedding space. The score is a ratio of Euclidean distances:

```
SGI = dist(response, question) / dist(response, context)
```

SGI > 1.0 means the response is geometrically closer to the context than to the question. The model engaged with the source material. SGI < 1.0 means it did not.

This is deterministic. Given the same inputs and the same embedding model, you get the same score every time. You can explain exactly why: "the response embedding was X units from the context and Y units from the question."

### DGI -- Directional Grounding Index

DGI works without context. It measures whether the displacement vector from question to response aligns with the characteristic direction of verified grounded responses:

```
delta = phi(response) - phi(question)
DGI = dot(normalize(delta), mu_hat)
```

The reference direction `mu_hat` is computed from calibration data -- verified correct question-response pairs. DGI checks whether new responses follow the same geometric pattern.

Generic calibration achieves AUROC ~0.76. Domain-specific calibration (20-100 verified pairs from your domain) reaches 0.90-0.99.

### What makes this work

- **Single embedding model.** `all-MiniLM-L6-v2` is 80MB. No GPU required. Sub-second inference.
- **Deterministic.** Same inputs always produce the same score. Reproducible across runs, machines, and time.
- **Auditable.** Every score decomposes into distances and angles that can be inspected, logged, and explained.
- **Domain-adaptable.** Calibration with a small set of verified pairs from your domain transforms generic detection into domain-expert detection.

## What groundlens is not

groundlens is not a replacement for human review. It is a triage tool. It tells you which outputs to review first, not which outputs are definitively wrong. The scores are geometric measurements, not truth claims.

The value proposition is verification triage: prioritize what to review, flag what diverges from expected patterns, and let human experts focus their attention where it matters most.

## Research roadmap

### Completed

- SGI for grounded hallucination detection in RAG pipelines (arXiv:2512.13771)
- DGI for context-free hallucination detection via directional analysis (arXiv:2602.13224)
- Confabulation boundary characterization via rotational dynamics (arXiv:2603.13259)
- Domain calibration framework achieving AUROC 0.90-0.99

### Active research

- **Multi-scale geometry.** SGI and DGI operate on single embedding vectors. Investigating hierarchical decomposition -- sentence-level, paragraph-level, document-level -- to catch hallucinations that are locally coherent but globally inconsistent.
- **Temporal drift detection.** Tracking how the reference direction `mu_hat` shifts over time as models are updated. This has implications for calibration maintenance in production systems.
- **Cross-model transfer.** Understanding how well calibration data from one embedding model transfers to another. Initial results suggest the geometric patterns are partially model-invariant.
- **Confabulation taxonomy.** Extending the geometric taxonomy to classify hallucination types (entity substitution, temporal confusion, causal inversion) based on the direction and magnitude of displacement vectors.

### Future directions

- **Streaming detection.** Token-level geometric monitoring during generation, enabling early stopping before a hallucination is fully generated.
- **Multi-modal grounding.** Extending geometric methods to vision-language models where the embedding space includes both text and image modalities.
- **Federated calibration.** Privacy-preserving calibration across organizations that share domain vocabulary but cannot share data.

## Community vision

groundlens is built on published research with open methods. The goal is a community of practitioners and researchers who:

- Contribute domain-specific calibration datasets (anonymized) to improve generic baselines
- Report real-world performance metrics across industries and use cases
- Extend the geometric framework to new modalities and scoring methods
- Challenge and improve the underlying mathematics through reproducible experiments

The strongest version of this library will be built by people who use it in production and share what they learn.
