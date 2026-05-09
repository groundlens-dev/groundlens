<div align="center">
  <img src="docs/assets/Logo_groundlens_white_background.png" alt="groundlens" width="200">
</div>

# Geometric LLM hallucination detection. No second LLM. Deterministic. Auditable.



[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](https://opensource.org/licenses/MIT)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![Version](https://img.shields.io/badge/version-2026.4.22-orange?style=flat-square)](https://github.com/groundlens-dev/groundlens/releases)

[Documentation](https://docs.groundlens.dev) | [Research Papers](#research) | [Examples](examples/) | [Contributing](CONTRIBUTING.md)

</div>

---

***groundlens*** detects LLM hallucinations using embedding geometry instead of a second LLM. It computes deterministic, auditable scores from the spatial relationships between questions, responses, and source context in an embedding space. The result is a verification signal you can explain in an audit, reproduce on demand, and run in regulated environments.

## Why ***groundlens***?

| Problem | How groundlens solves it |
|---|---|
| Second-LLM judges are non-deterministic and expensive | Single embedding model (`all-MiniLM-L6-v2`), deterministic output, sub-second latency |
| Probabilistic scores cannot be audited | Geometric ratios and angular measurements with clear mathematical definitions |
| Regulatory compliance requires explainability | Every score traces to Euclidean distances and cosine similarities in $R^n$ |
| One method does not fit all use cases | SGI for RAG/context verification, DGI for context-free chat, `evaluate()` auto-selects |

`SGI`: Semantic Grounding Index | `DGI`: Directional Grounding Index


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

**Domain calibration** improves DGI accuracy from AUROC ~0.8 with a basic calibration to 0.90-0.99 with domain-sepecific calibration:

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

## Architecture

```
groundlens/
├── __init__.py              # Public API: compute_sgi, compute_dgi, evaluate, calibrate
├── sgi.py                   # Semantic Grounding Index (context-required)
├── dgi.py                   # Directional Grounding Index (context-free)
├── evaluate.py              # High-level evaluate() and evaluate_batch()
├── calibrate.py             # Domain-specific DGI calibration
├── score.py                 # Result types: SGIResult, DGIResult, GroundlensScore
├── _version.py              # CalVer version (2026.4.22)
├── _internal/               # Private implementation
│   ├── geometry.py          # Euclidean distance, displacement, unit normalize
│   ├── embeddings.py        # Sentence transformer encoding
│   ├── thresholds.py        # Decision boundaries and normalization
│   └── csv_loader.py        # Calibration data loading
├── cli/
│   └── main.py              # CLI: check, evaluate, calibrate, benchmark
├── providers/               # LLM provider wrappers
│   ├── _base.py             # BaseLLMProvider protocol + LLMResponse
│   ├── openai.py            # OpenAI provider
│   ├── anthropic.py         # Anthropic provider
│   └── google.py            # Google Generative AI provider
└── integrations/            # Framework integrations
    ├── langchain/           # LangChain evaluator + callback
    ├── crewai/              # CrewAI tool
    ├── semantic_kernel/     # Semantic Kernel filter
    └── autogen/             # AutoGen checker
```

The architecture follows a layered design:

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

## Scoring methods

### SGI (Semantic Grounding Index)

```
SGI = dist(phi(response), phi(question)) / dist(phi(response), phi(context))
```

| Score | Interpretation |
|---|---|
| SGI > 1.20 | Strong context engagement (pass) |
| 0.95 < SGI < 1.20 | Partial engagement (review recommended) |
| SGI < 0.95 | Weak engagement (flagged) |

### DGI (Directional Grounding Index)

```
delta = phi(response) - phi(question)
DGI = dot(delta / ||delta||, mu_hat)
```

| Score | Interpretation |
|---|---|
| DGI > 0.30 | Aligns with grounded patterns (pass) |
| 0.00 < DGI < 0.30 | Weak alignment (flagged) |
| DGI < 0.00 | Opposes grounded direction (high risk) |

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

## Research

groundlens implements the methods described in three peer-reviewed papers:

1. **Semantic Grounding Index (SGI)**
   Marin, J. (2025). *Semantic Grounding Index for LLM Hallucination Detection.*
   [arXiv:2512.13771](https://arxiv.org/abs/2512.13771)

2. **Directional Grounding Index (DGI)**
   Marin, J. (2026). *A Geometric Taxonomy of Hallucinations in Large Language Models.*
   [arXiv:2602.13224](https://arxiv.org/abs/2602.13224)

3. **Confabulation Benchmark**
   Marin, J. (2026). *Rotational Dynamics of Factual Constraint Processing in Large Language Models.*
   [arXiv:2603.13259](https://arxiv.org/abs/2603.13259)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code standards, and PR process.

## License

[MIT](LICENSE) -- Javier Marin (javier@jmarin.info)
