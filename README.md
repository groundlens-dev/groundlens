<div align="center">
  <img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/Logo_groundlens_new-05.png" alt="groundlens" width="250">
</div>

# Geometric LLM hallucination detection. No second LLM. Deterministic. Auditable.

<div align="center">

[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![codecov](https://codecov.io/gh/groundlens-dev/groundlens/branch/main/graph/badge.svg)](https://codecov.io/gh/groundlens-dev/groundlens)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![Version](https://img.shields.io/badge/version-2026.4.22-orange?style=flat-square)](https://github.com/groundlens-dev/groundlens/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](https://opensource.org/licenses/MIT)

[Documentation](https://docs.groundlens.dev) | [Research Papers](#research) | [Examples](examples/) | [Vision](VISION.md) | [Contributing](CONTRIBUTING.md)

</div>

---

Groundlens detects LLM hallucinations using embedding geometry instead of a second LLM. It computes deterministic, auditable scores from the spatial relationships between questions, responses, and source context in an embedding space. The result is a verification signal you can explain in an audit, reproduce on demand, and run in regulated environments.

## Why ***groundlens***?

| Problem | How groundlens solves it |
|---|---|
| Second-LLM judges are non-deterministic and expensive | Single embedding model (`all-MiniLM-L6-v2`), deterministic output, sub-second latency |
| Probabilistic scores cannot be audited | Geometric ratios and angular measurements with clear mathematical definitions |
| Regulatory compliance requires explainability | Every score traces to Euclidean distances and cosine similarities in $\mathbf{R}^n$ (n-dimensional real vector space query/anwser)|
| One method does not fit all use cases | SGI for RAG/context verification, DGI for context-free chat, `evaluate()` auto-selects |

`SGI`: Semantic Grounding Index | `DGI`: Directional Grounding Index

## I want to...

| Goal | Start here |
|---|---|
| **Verify my RAG pipeline outputs** | [SGI quick start](#sgi----with-context-rag-verification) · [RAG verification guide](https://docs.groundlens.dev/guides/rag-verification/) |
| **Score chat responses without context** | [DGI quick start](#dgi----without-context) · [DGI deep dive](https://docs.groundlens.dev/concepts/dgi/) |
| **Evaluate a batch of outputs** | [Batch evaluation](#batch-evaluation) · [Batch guide](https://docs.groundlens.dev/guides/batch-evaluation/) |
| **Wrap my LLM provider with auto-scoring** | [Provider guard](#llm-provider-guard) · [Providers docs](https://docs.groundlens.dev/providers/openai/) |
| **Integrate with LangChain / CrewAI / etc.** | [Integrations](#providers-and-integrations) · [Integration docs](https://docs.groundlens.dev/integrations/langchain/) |
| **Improve accuracy for my domain** | [Domain calibration](#domain-calibration) · [Calibration guide](https://docs.groundlens.dev/guides/domain-calibration/) |
| **Comply with the EU AI Act** | [EU AI Act guide](https://docs.groundlens.dev/guides/eu-ai-act/) |
| **Understand the math** | [How it works](https://docs.groundlens.dev/concepts/how-it-works/) · [Research papers](#research) |
| **Understand what it can and cannot detect** | [Hallucination taxonomy](#taxonomy-of-llm-hallucinations) |
| **Check my environment is set up correctly** | [`groundlens doctor`](#cli) |
| **Contribute** | [CONTRIBUTING.md](CONTRIBUTING.md) · [CLAUDE.md](CLAUDE.md) · [AGENTS.md](AGENTS.md) |

## Installation

```bash
pip install groundlens
```

With LLM provider support:

```bash
pip install "groundlens[openai]"       # OpenAI
pip install "groundlens[anthropic]"    # Anthropic
pip install "groundlens[google]"       # Google Generative AI
pip install "groundlens[providers]"    # All providers
```

With framework integrations:

```bash
pip install "groundlens[langchain]"    # LangChain
pip install "groundlens[crewai]"       # CrewAI
pip install "groundlens[semantic-kernel]"  # Semantic Kernel
pip install "groundlens[autogen]"      # AutoGen
pip install "groundlens[all]"          # Everything
```

**Requirements:** Python 3.10+, numpy, sentence-transformers.

## Quick start

### SGI -- with context (RAG verification)

SGI (Semantic Grounding Index) measures whether a response engaged with the provided context or stayed anchored to the question. It requires three inputs.

```python
from groundlens import compute_sgi

result = compute_sgi(
    question="What is the capital of France?",
    context="France is in Western Europe. Its capital is Paris.",
    response="The capital of France is Paris.",
)

print(result.value)       # 1.23 — ratio of distances
print(result.normalized)  # 0.61 — mapped to [0, 1]
print(result.flagged)     # False — above review threshold
print(result.explanation) # "SGI=1.230 — strong context engagement (pass)"
```

**Interpretation:** `SGI > 1.0` means the response is closer to the context than to the question in embedding space. The response engaged with the source material.

### DGI -- without context

DGI (Directional Grounding Index) detects hallucinations without requiring source context. It checks whether the question-to-response displacement vector aligns with the characteristic direction of verified grounded responses.

```python
from groundlens import compute_dgi

result = compute_dgi(
    question="What causes seasons on Earth?",
    response="Seasons are caused by Earth's 23.5-degree axial tilt.",
)

print(result.value)       # 0.42 — cosine similarity to reference direction
print(result.normalized)  # 0.71 — mapped to [0, 1]
print(result.flagged)     # False — above pass threshold (0.30)
```

**Domain calibration** improves DGI accuracy from AUROC ~0.8 with a basic calibration to 0.90-0.99 with domain-specific calibration:

```python
from groundlens import compute_dgi

result = compute_dgi(
    question="What is the statute of limitations for breach of contract in California?",
    response="Four years under California Code of Civil Procedure Section 337.",
    reference_csv="legal_calibration_pairs.csv",
)
```

### evaluate() -- auto-select

The `evaluate()` function picks the right method automatically: SGI when context is provided, DGI when it is not.

```python
from groundlens import evaluate

# With context -> SGI
score = evaluate(
    question="What is X?",
    response="X is Y.",
    context="According to the manual, X is Y.",
)
assert score.method == "sgi"

# Without context -> DGI
score = evaluate(
    question="What is X?",
    response="X is Y.",
)
assert score.method == "dgi"
```

### Batch evaluation

```python
from groundlens import evaluate_batch

items = [
    {"question": "Q1?", "response": "A1.", "context": "Source."},
    {"question": "Q2?", "response": "A2."},
    {"question": "Q3?", "response": "A3.", "context": "Reference."},
]

results = evaluate_batch(items)
flagged = [r for r in results if r.flagged]
print(f"{len(flagged)}/{len(results)} flagged for review")
```

### CLI

```bash
# Check environment health
groundlens doctor

# Single response check
groundlens check \
  --question "What is the capital of France?" \
  --response "The capital of France is Paris." \
  --context "France is in Western Europe. Its capital is Paris."

# Batch CSV evaluation
groundlens evaluate input.csv --output results.csv

# Domain calibration
groundlens calibrate --pairs domain_pairs.csv --output calibration.json

# Run the confabulation benchmark
groundlens benchmark
```

### LLM provider guard

```python
from groundlens.providers.openai import OpenAIProvider

provider = OpenAIProvider(model="gpt-4o")
response = provider.complete(
    prompt="Summarize this document.",
    context="The document text here...",
)

if response.groundlens_score and response.groundlens_score.flagged:
    print("Hallucination risk detected — review recommended.")
else:
    print(response.text)
```

## Taxonomy of LLM hallucinations

Not all hallucinations are the same. Groundlens is built on a [geometric taxonomy](https://docs.groundlens.dev/theory/hallucination-taxonomy/) ([arXiv:2602.13224](https://arxiv.org/pdf/2602.13224v3)) that classifies hallucinations by their geometric signature in embedding space — which determines whether they are detectable and which scoring method applies.

<div align="center">
  <img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/taxonomy.png" alt="Hallucination taxonomy on the unit hypersphere" width="480">
  <br>
  <sub>Every text maps to a point on the hypersphere S<sup>d−1</sup>. The question <b>q</b> and context <b>c</b> define a geodesic arc. Grounded responses (blue) fall inside the plausibility region 𝒫<sub>q</sub>. <b>Type I</b> (purple) stays near q — the response ignored the context. <b>Type II</b> (red) deviates far from both q and c — invented content. <b>Type III</b> (pink) lands inside 𝒫<sub>q</sub> alongside the correct answer — same vocabulary and structure, wrong facts, geometrically indistinguishable.</sub>
</div>
<br>

| Type | What happens | Example | Detection |
|---|---|---|---|
| **Type I — Unfaithfulness** | Response ignores the provided source and defaults to the question | RAG system returns an answer from memory instead of from the retrieved document | **SGI** (distance ratio) |
| **Type II — Confabulation** | Response invents content outside the topic's vocabulary | Asked about CRISPR gene editing, the model describes protein-folding correction instead | **DGI** (displacement direction) |
| **Type III — Within-frame error** | Response uses the right vocabulary and structure but gets the facts wrong | "The capital of Australia is Canberra" vs. "The capital of Australia is Sydney" — same frame, wrong city | **Undetectable by geometry** |

**Why Type III is undetectable:** Sentence embeddings encode distributional similarity (vocabulary, syntax, co-occurrence), not truth value. Two responses that share the same words, entities, and syntactic frame land in the same region of embedding space regardless of which one is correct. This is not a limitation of groundlens — it is a property of the distributional hypothesis (Harris, 1954) that constrains every embedding-based method, including NLI (which *inverts* to AUROC 0.311 on TruthfulQA, actively favoring false answers over truthful ones).

**Implications:** Groundlens is **verification triage** — it detects the hallucination types that leave geometric traces (Types I and II), which are the most common and most damaging in production. For Type III errors in high-stakes domains (medical, legal, financial), complement groundlens with claim-level fact-checking tools on the outputs that pass geometric verification. See [Complementary Tools for Type III](https://docs.groundlens.dev/theory/confabulation-boundary/#complementary-tools-for-type-iii-detection).

## Scoring methods

Each scoring method targets a specific hallucination type from the taxonomy above.

### SGI (Semantic Grounding Index) — detects Type I

When context is available, SGI measures whether the response engaged with the source or stayed anchored to the question:

```
SGI = dist(phi(response), phi(question)) / dist(phi(response), phi(context))
```

| Score | Interpretation |
|---|---|
| SGI > 1.20 | Strong context engagement (pass) |
| 0.95 < SGI < 1.20 | Partial engagement (review recommended) |
| SGI < 0.95 | Weak engagement (flagged — possible Type I) |

### DGI (Directional Grounding Index) — detects Type II

When no context is available, DGI checks whether the question-to-response displacement aligns with a learned "grounded direction":

```
delta = phi(response) - phi(question)
DGI = dot(delta / ||delta||, mu_hat)
```

| Score | Interpretation |
|---|---|
| DGI > 0.30 $^1$ | Aligns with grounded patterns (pass) |
| 0.00 < DGI < 0.30 | Weak alignment (flagged — possible Type II) |
| DGI < 0.00 | Opposes grounded direction (high risk) |

$^1$ This score corresponds to a general calibration. In domain-specific calibrations the score can vary.

## Providers and integrations

| Component | Install extra | Description |
|---|---|---|
| OpenAI | `openai` | Wraps `openai` SDK with automatic scoring |
| Anthropic | `anthropic` | Wraps `anthropic` SDK with automatic scoring |
| Google | `google` | Wraps `google-generativeai` with automatic scoring |
| LangChain | `langchain` | Evaluator + callback handler |
| CrewAI | `crewai` | Tool for agent pipelines |
| Semantic Kernel | `semantic-kernel` | Function calling filter |
| AutoGen | `autogen` | Agent chat checker |

## Domain calibration

Generic DGI uses a bundled reference direction that achieves AUROC ~0.8 with a basic calibration. For production use, a domain-specific calibration can be applied (a minimum of 200 queries recommended):

```python
from groundlens import calibrate

result = calibrate(csv_path="my_domain_pairs.csv")
print(f"Concentration: {result.concentration:.2f}")
result.save("calibration.json")
```

Domain-specific calibration typically reaches AUROC 0.90-0.99. The confabulation benchmark (arXiv:2603.13259) reports DGI AUROC 0.958 with domain calibration.

## Architecture

```
┌─────────────────────────────────────────────┐
│            Public API (evaluate)            │
├──────────────────┬──────────────────────────┤
│   SGI (sgi.py)   │      DGI (dgi.py)        │
├──────────────────┴──────────────────────────┤
│        _internal (geometry, embeddings)     │
├─────────────────────────────────────────────┤
│  sentence-transformers (all-MiniLM-L6-v2)   │
└─────────────────────────────────────────────┘
         ▲                           ▲
         │                           │
   ┌─────┴──────┐            ┌───────┴──────┐
   │ Providers  │            │ Integrations │
   │ (OpenAI,   │            │ (LangChain,  │
   │  Anthropic,│            │  CrewAI,     │
   │  Google)   │            │  SK, AutoGen │
   └────────────┘            └──────────────┘
```

See [AGENTS.md](AGENTS.md) for detailed file-by-file documentation. See [CLAUDE.md](CLAUDE.md) for AI-assisted development guidelines.

## Research

groundlens implements the methods described in three research papers:

1. **Semantic Grounding Index (SGI)**
   Marin, J. (2025). *Semantic Grounding Index for LLM Hallucination Detection.*
   [arXiv:2512.13771](https://arxiv.org/abs/2512.13771)

2. **Directional Grounding Index (DGI)**
   Marin, J. (2026). *A Geometric Taxonomy of Hallucinations in Large Language Models.*
   [arXiv:2602.13224](https://arxiv.org/pdf/2602.13224v3)

3. **Mechanistic Interpretability**
   Marin, J. (2026). *Rotational Dynamics of Factual Constraint Processing in Large Language Models.*
   [arXiv:2603.13259](https://arxiv.org/abs/2603.13259)

4. **Hallucination Benchmark**
https://github.com/groundlens-dev/grounding-benchmark/blob/4abf98ec5d2f846850a44f713115323659c2a793/paper/A_Methodology_for_Building_Human_Confabulated_Hallucination_Benchmarks.pdf
   
## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting, scope, and response timelines.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code standards, and PR process.

```bash
# Quick start for contributors
git clone https://github.com/groundlens-dev/groundlens.git
cd groundlens
pip install -e ".[dev]"
pre-commit install
groundlens doctor     # verify your environment
pytest tests/unit/    # run fast tests
```

## About

Groundlens is built and maintained by [Javier Marin](https://jmarin.info) -- an engineer who has reinvented himself more times than most people change jobs. The math comes from engineering, the skepticism from regulated industries, and the stubbornness from experience. Read the [origin story](VISION.md#origin).

## License

[MIT](LICENSE) -- Javier Marin (javier@jmarin.info)
