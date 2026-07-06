# Groundlens

<div align="center">
  <img src="assets/Logo_groundlens_new-05.png" alt="groundlens" width="200">
</div>

## Geometric LLM hallucination detection. No second LLM. Deterministic. Auditable.

---

Groundlens is a Python library that detects hallucinations in LLM outputs using embedding geometry rather than a second language model. It provides two complementary scoring methods:

- **SGI (Semantic Grounding Index)** --- measures whether a response engaged with provided source context, using distance ratios in embedding space.
- **DGI (Directional Grounding Index)** --- evaluates response grounding without any context, using directional statistics on displacement vectors.

Both methods are deterministic, sub-second, and produce auditable numeric scores --- no black-box LLM-as-judge.

## Key Features

| Feature | Description |
|---|---|
| **Two scoring modes** | SGI (with context) and DGI (context-free) cover all verification scenarios |
| **Deterministic** | Same inputs always produce the same score --- no sampling variance |
| **Sub-second** | Sentence-transformer inference, not LLM generation |
| **Domain calibration** | Generic AUROC ~0.8; domain-specific calibration reaches 0.90--0.99 |
| **EU AI Act ready** | No opaque second LLM --- fully auditable decision pipeline |
| **Provider wrappers** | OpenAI, Anthropic, Google Gemini with automatic scoring |
| **Framework integrations** | LangChain, CrewAI, Semantic Kernel, AutoGen |

## Quick Install

```bash
pip install groundlens
```

For provider-specific extras:

```bash
pip install "groundlens[openai]"       # OpenAI provider
pip install "groundlens[langchain]"    # LangChain integration
pip install "groundlens[all]"          # Everything
```

## 3-Line Example

```python
from groundlens import evaluate

score = evaluate(
    question="What is the capital of France?",
    response="The capital of France is Paris.",
    context="France is in Western Europe. Its capital is Paris.",
)
print(score.flagged)   # False
print(score.method)    # 'sgi'
print(score.value)     # 1.23 (example)

# ...or a plain-language reading for a person:
from groundlens import check
print(check(score).line())
# CHECK: Supported by the document (Semantic Grounding Index - SGI=1.23)
```

## Setup in 30 Seconds

1. **Embed** the question, response, and (optionally) context into $\mathbb{R}^n$ using a sentence transformer.
2. **Compute a geometric score**:
    - *With context*: SGI = ratio of distances --- is the response closer to context or to the question?
    - *Without context*: DGI = cosine similarity of the question-to-response displacement against a calibrated reference direction.
3. **Flag** responses that fall below empirically-derived thresholds.

No token generation. No prompt engineering. No stochastic sampling. Pure geometry.

## Research Papers

| Paper | Index | arXiv |
|---|---|---|
| Semantic Grounding Index for LLM Hallucination Detection | SGI | [2512.13771](https://arxiv.org/abs/2512.13771) |
| A Geometric Taxonomy of Hallucinations in LLMs | DGI | [2602.13224](https://arxiv.org/pdf/2602.13224v3) |
| Rotational Dynamics of Factual Constraint Processing | Confabulation benchmark | [2603.13259](https://arxiv.org/abs/2603.13259) |

## Author

**Javier Marin** --- [javier@groundlens.dev](mailto:javier@jgroundlens.dev) and [javier@jmarin.info](mailto:javier@jmarin.info)

---

*Groundlens is part of the [CERT Framework](https://github.com/groundlens-dev/groundlens) for verification triage --- helping teams prioritize which LLM outputs need human review.*
