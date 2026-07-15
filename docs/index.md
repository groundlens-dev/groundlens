# Groundlens

<div align="center">
  <img src="assets/logo.png" alt="groundlens" width="200">

# Deterministic first-stage hallucination triage. It decides what your expensive check has to look at. Single-pass, auditable.

</div>

Groundlens is a Python library that triages LLM outputs using embedding geometry, so an expensive second-stage check (an LLM judge or a human reviewer) runs only on the outputs that actually need it. It provides two complementary scoring methods:

- **SGI (Semantic Grounding Index)** --- measures whether a response engaged with provided source context, using distance ratios in embedding space.
- **DGI (Directional Grounding Index)** --- evaluates response grounding without any context, using directional statistics on displacement vectors.

Both methods are deterministic, sub-second, and produce auditable numeric scores. Groundlens runs *before* any LLM-as-judge, not instead of one: it is the deterministic filter that decides what the expensive check even has to look at.

## Why Groundlens
Groundlens is **Stage 1**: a deterministic, single-pass, no-judge filter that catches semantic disengagement, whether an answer actually engaged its source. It does not verify facts. A plausible wrong fact stated in the right frame (in-register substitution) is provably invisible to any embedding method and must be escalated to **Stage 2**, an LLM judge or a human. Groundlens makes that expensive stage affordable by shrinking what it has to check.

## Key Features

| Feature | Description |
|---|---|
| **MCP available** | [Groundlens MCP](https://github.com/groundlens-dev/groundlens-mcp) |
| **Two scoring modes** | SGI (with context) and DGI (context-free) cover all verification scenarios |
| **Deterministic** | Same inputs always produce the same score --- no sampling variance |
| **Sub-second** | Sentence-transformer inference, not LLM generation |
| **Domain calibration** | SGI accepts domain calibration to reach AUROC > 0.8 | 
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

## Basic example

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

## Quick Setup

1. **Embed** the question, response, and (optionally) context into $\mathbb{R}^n$ using a sentence transformer.
2. **Compute a geometric score**:
    - *With context*: SGI = ratio of distances --- is the response closer to context or to the question?
    - *Without context*: DGI = cosine similarity of the question-to-response displacement against a calibrated reference direction.
3. **Flag** responses that fall below empirically-derived thresholds.

No token generation. No prompt engineering. No stochastic sampling. Pure geometry.

## Research Papers

| Paper | Index | Preprint |
|---|---|---|
| Semantic Grounding Index for LLM Hallucination Detection | SGI | [2512.13771](https://arxiv.org/abs/2512.13771) |
| A Geometric Taxonomy of Hallucinations in LLMs | DGI | [2602.13224](https://arxiv.org/pdf/2602.13224v3) |
| How Transformers Reject Wrong Answers: Rotational Dynamics of Factual Constraint Processing | Mechanistic Interpretability | [2603.13259](https://arxiv.org/abs/2603.13259) |

## Contributing to Groundlens

All contributions, bug reports, bug fixes, documentation improvements, enhancements, and ideas are welcome. A detailed overview on how to contribute can be found in the contributing guide.

If you are simply looking to start working with the pandas codebase, navigate to the GitHub "issues" tab and start looking through interesting issues. There are a number of issues listed under Docs and good first issue where you could start out.

Feel free to ask questions: [javier@groundlens.dev](mailto:javier@groundlens.dev) / [javier@jmarin.info](mailto:javier@jmarin.info)


*As contributors and maintainers to this project, you are expected to abide by groundlens' code of conduct. More information can be found at: Contributor Code of Conduct*
