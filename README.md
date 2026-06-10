<div align="center">
<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/Logo_groundlens_new-05.png" alt="groundlens" width="250">

# Groundlens
</div>

## Triage for AI agents and model outputs. Deterministic. Auditable. No second LLM.

<div align="center">

[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![codecov](https://codecov.io/gh/groundlens-dev/groundlens/branch/main/graph/badge.svg)](https://codecov.io/gh/groundlens-dev/groundlens)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![Version](https://img.shields.io/badge/version-2026.6.10-orange?style=flat-square)](https://github.com/groundlens-dev/groundlens/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](https://opensource.org/licenses/MIT)

[Documentation](https://docs.groundlens.dev) | [Research Papers](#research) | [Examples](examples/) | [Vision](VISION.md) | [Contributing](CONTRIBUTING.md)

</div>

---

Most teams evaluate LLM responses with another LLM. That doesn't survive an audit. Groundlens replaces the judge with a geometric scorer: every response gets a deterministic, sub-second grounding score so humans review the bottom percentile, not everything. No second LLM in the loop. Designed for production deployment in regulated industries.

Groundlens is **triage** — *pay immediate attention to particular priorities*. It does not classify responses as right or wrong. It ranks them by grounding signal, exposes the riskiest first, and stays out of the human reviewer's way for the rest.

Modern AI systems are agentic pipelines, not single models. Groundlens triages outputs from individual LLMs **and** from multi-agent deployments: routing / intent agents, RAG / informational agents, and specialized / tool-using agents each get their own rule set.

## Why triage instead of an LLM judge?

| Problem with LLM-as-judge | The triage approach |
|---|---|
| Non-deterministic — same response, different verdict next month | Same input → same score, byte-identical, indefinitely. Reproducible across years for audit. |
| Circular — the judge LLM has the same failure modes as the LLM it judges | Geometric scorer over embedding space. No second LLM in the loop. |
| Doesn't scale — $0.05–$0.20 per call × 1M responses/month = $50K–$200K/month just to validate | Sub-second per response, marginal cost ~$0 post-deployment. Score every output, not a sample. |
| Binary verdicts hide nuance, force arbitrary thresholds | Continuous score for ranking. Review the bottom percentile of your batch — the threshold is operational, not metaphysical. |
| Comparable historicals are lost when you upgrade the judge | Pure embedding geometry. Method does not change with model upgrades. Time-series analysis stays valid. |
| Agentic pipelines are black boxes | LangGraph callback auto-scores every LLM call with per-node triage and structured traces. |

`SGI`: Semantic Grounding Index (with context) | `DGI`: Directional Grounding Index (without context)

## I want to...

| Goal | Start here |
|---|---|
| **Triage my RAG pipeline outputs** | [SGI quick start](#sgi----with-context-rag-verification) · [RAG triage guide](https://docs.groundlens.dev/guides/rag-verification/) |
| **Score chat responses without context** | [DGI quick start](#dgi----without-context) · [DGI deep dive](https://docs.groundlens.dev/concepts/dgi/) |
| **Score every LLM call in my LangGraph agent** | [LangGraph quick start](#langgraph----agentic-pipeline-scoring) · [LangGraph docs](https://docs.groundlens.dev/integrations/langgraph/) |
| **Rank a batch of outputs for review** | [Batch evaluation](#batch-evaluation) · [Batch guide](https://docs.groundlens.dev/guides/batch-evaluation/) |
| **Wrap my LLM provider with auto-scoring** | [Provider guard](#llm-provider-guard) · [Providers docs](https://docs.groundlens.dev/providers/openai/) |
| **Integrate with LangChain / CrewAI / etc.** | [Integrations](#providers-and-integrations) · [Integration docs](https://docs.groundlens.dev/integrations/langchain/) |
| **Improve accuracy for my domain** | [Domain calibration](#domain-calibration) · [Calibration guide](https://docs.groundlens.dev/guides/domain-calibration/) |
| **Deploy in regulated banking** | [Banking deployment guide](https://docs.groundlens.dev/guides/banking-deployment/) |
| **Comply with the EU AI Act** | [EU AI Act guide](https://docs.groundlens.dev/guides/eu-ai-act/) |
| **Comply with SR 11-7 (US model risk)** | [SR 11-7 guide](https://docs.groundlens.dev/guides/sr-11-7/) |
| **Map to NIST AI RMF** | [NIST AI RMF guide](https://docs.groundlens.dev/guides/nist-ai-rmf/) |
| **Triage with audit-trail rules** | [Rule sets quick start](#rule-sets----audit-trail-triage) · [`groundlens.rules`](https://docs.groundlens.dev/concepts/rules/) |
| **Triage a routing / intent agent** | [`routing_rules()`](#agents) · [`groundlens.agents`](https://docs.groundlens.dev/concepts/agents/) |
| **Triage a RAG / informational agent** | [`rag_rules()`](#agents) · [`groundlens.agents`](https://docs.groundlens.dev/concepts/agents/) |
| **Triage a specialized / tool-using agent** | [`specialized_agent_rules()`](#agents) · [`groundlens.agents`](https://docs.groundlens.dev/concepts/agents/) |
| **Build my own rule set for legal / insurance / healthcare** | [Custom rule sets](#custom-rule-sets) · [examples/custom_rules.py](examples/custom_rules.py) |
| **Map decisions to specific regulatory clauses** | [`groundlens.compliance`](https://docs.groundlens.dev/concepts/compliance/) · [Audit log](https://docs.groundlens.dev/concepts/audit/) |
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
pip install "groundlens[openai]"          # OpenAI
pip install "groundlens[anthropic]"       # Anthropic
pip install "groundlens[google]"          # Google Generative AI
pip install "groundlens[providers]"       # All providers
```

With framework integrations:

```bash
pip install "groundlens[langgraph]"       # LangGraph (agentic pipelines)
pip install "groundlens[langchain]"       # LangChain
pip install "groundlens[crewai]"          # CrewAI
pip install "groundlens[semantic-kernel]" # Semantic Kernel
pip install "groundlens[autogen]"         # AutoGen
pip install "groundlens[all]"             # Everything
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

print(result.value)        # 1.23 — ratio of distances
print(result.normalized)   # 0.61 — mapped to [0, 1]
print(result.flagged)      # False — above review threshold
print(result.explanation)  # "SGI=1.230 — strong context engagement (pass)"
```

**Interpretation:** SGI is a continuous score, not a verdict. Higher values mean the response engaged more with the source material than with the question. Use SGI for ranking and triage; default thresholds (`flagged`, `review`, `trusted`) are provided as interpretation aids but can be tuned to your operating point.

### DGI -- without context

DGI (Directional Grounding Index) detects hallucinations without requiring source context. It checks whether the question-to-response displacement vector aligns with the characteristic direction of verified grounded responses.

```python
from groundlens import compute_dgi

result = compute_dgi(
    question="What causes seasons on Earth?",
    response="Seasons are caused by Earth's 23.5-degree axial tilt.",
)

print(result.value)        # 0.42 — cosine similarity to reference direction
print(result.normalized)   # 0.71 — mapped to [0, 1]
print(result.flagged)      # False — above pass threshold (0.30)
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

### LangGraph -- agentic pipeline scoring

LangGraph agents chain multiple LLM calls through tool-use, retrieval, and reasoning nodes. Groundlens intercepts every LLM call, auto-selects SGI or DGI based on available context, and builds a structured trace with per-node triage labels.

```python
from langgraph.graph import StateGraph
from groundlens.integrations.langgraph import GroundlensLangGraphCallback

# Attach the callback to your LangGraph agent
callback = GroundlensLangGraphCallback()
app = graph.compile()
result = app.invoke({"messages": [...]}, config={"callbacks": [callback]})

# Get the structured trace
trace = callback.get_trace()
print(trace.summary())
# "3 steps | 2 trusted, 1 flagged | retriever [SGI=1.30 trusted], ..."

# Triage: which nodes need review?
for step in trace.steps:
    if step.triage == "flagged":
        print(f"  {step.node_name}: {step.method}={step.score.value:.3f}")

# Export an interactive HTML report
trace.to_html(path="triage_report.html")

# Or get structured data for logging
trace.to_json()  # JSON string
trace.to_dict()  # Python dict
```

The callback hooks into LangGraph's lifecycle events. When a tool produces output, it becomes the context for the next LLM call (scored with SGI). When no tool output is available, the LLM call is scored with DGI. Each step gets a triage label so the reviewer goes straight to the nodes that matter.

In a multi-step agent, a hallucination in step 2 can cascade through steps 3-5 and produce a confidently wrong final answer. Groundlens gives you per-node visibility so you can catch problems where they originate, not after they compound.

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

# Triage: sort by SGI, review the bottom percentile
sorted_results = sorted(results, key=lambda r: r.score.value)
to_review = sorted_results[:max(1, len(sorted_results) // 20)]   # bottom 5%
print(f"{len(to_review)}/{len(results)} flagged for human review")
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
    print("Low-grounding response — surface for human review.")
else:
    print(response.text)
```

### Rule sets -- audit-trail triage

Geometric scores rank responses by grounding signal. Rule sets complement that with an **auditable per-rule trail** — for each response, every rule that fired or didn't is recorded, with the matched evidence span and a citation to the academic, industrial, or regulatory source that motivates the rule.

```python
from groundlens import groundlens_banking_rules

ruleset = groundlens_banking_rules()  # 20 rules, 5 sub-scores

result = ruleset.evaluate(
    question="Should this client be approved for credit?",
    response=(
        "Recommend escalation because the AML flag is triggered "
        "(page 4 of the policy). Bureau A reports risk score 0.75. "
        "Confidence of 80% pending independent review."
    ),
    context="Page 4 of policy: AML flag triggers human review. Bureau A: 0.75 risk score.",
    metadata={"flags_present": ["AML"]},
)

print(result.sub_scores)
# {'groundedness': 0.65, 'completeness': 0.40, 'calibration': 0.55,
#  'traceability': 0.85, 'robustness': 1.00}
print(result.flagged)            # False — passes the audit-defensibility floor
print(result.audit_explanation)  # Human-readable per-rule trail
```

`groundlens_banking_rules` is the current canonical 20-rule reference set for banking governance (credit, AML, KYC, fraud, sanctions, concentration, model risk). Each rule carries a `citation` field pointing to its provenance source. Sub-scores: **groundedness**, **completeness**, **calibration**, **traceability**, **robustness**. The flag predicate is non-compensatory: weakness in any regulator-non-negotiable dimension flags the response for review.

### Custom rule sets

The rule engine is domain-agnostic. `RuleSet` and `ChecklistRule` are composable primitives — you can build a rule set for any domain by writing pure-Python `check` functions and grouping them under your own sub-score categories.

```python
from groundlens import ChecklistRule, RuleEvidence, RuleSet

def _check_cites_clause(question, response, context, metadata):
    matched = "clause" in response.lower() or "§" in response
    return RuleEvidence(matched=matched, span="clause", explanation="cites a contract clause")

legal_ruleset = RuleSet(
    name="legal_contract_review_v1",
    rules=(
        ChecklistRule(
            id="legal.cites_clause",
            description="rationale cites a specific contract clause",
            weight=0.40,
            sub_score="traceability",
            check=_check_cites_clause,
            citation="ABA Model Rules of Professional Conduct, Rule 1.1 Competence",
        ),
        # ... add your own rules
    ),
    sub_scores=("groundedness", "traceability"),
)

result = legal_ruleset.evaluate(question=..., response=..., context=...)
```

See [examples/custom_rules.py](examples/custom_rules.py) for an end-to-end example.

## Agents

Modern AI systems are agentic pipelines, not single models. A production deployment like BBVA's Blue assistant runs three agent classes in concert — routing, RAG, and specialized — each with distinct failure modes and audit requirements. Groundlens ships one rule set per class:

| Agent class | Factory | Sub-scores | Targets |
|---|---|---|---|
| Routing / intent | [`routing_rules()`](src/groundlens/agents/routing.py) | intent_clarity, classification_confidence, fallback_appropriateness, disambiguation_quality | Mis-classification, over-use of fallback, silent routing on tight margins |
| RAG / informational | [`rag_rules()`](src/groundlens/agents/rag.py) | groundedness, completeness, calibration, traceability, robustness | Fabrication, omission, miscalibration on out-of-knowledge queries |
| Specialized / tool-using | [`specialized_agent_rules()`](src/groundlens/agents/specialized.py) | entity_groundedness, entity_completeness, entity_calibration, execution_readiness | Entity hallucination (IBAN, amount), premature execution, missing required fields |

Every rule carries a citation to its academic, industrial, or regulatory source — BBVA AI Factory's Blue Eval post, ISO 13616 IBAN standard, EBA Guidelines, Federal Reserve SR 26-2, NIST AI RMF, peer-reviewed NLP literature.

```python
from groundlens.agents import routing_rules, rag_rules, specialized_agent_rules

# Triage a routing decision
routing = routing_rules()
result = routing.evaluate(
    question="transfer 500 to my brother and check my balance",
    response="OK.",
    metadata={
        "predicted_intent": "transfer",
        "top1_score": 0.62,
        "margin": 0.08,
        "fallback_fired": False,
        "query_in_scope": True,
    },
)
assert result.flagged  # multi-intent query + low confidence

# Triage an entity-capture decision
specialized = specialized_agent_rules()
result = specialized.evaluate(
    question="send 500 to ES91 2100 0418 4502 0005 1332",
    response="Transferring 500 EUR.",
    metadata={
        "dialog": "send 500 to ES91 2100 0418 4502 0005 1332. yes confirm.",
        "entities": {"amount": 500, "iban": "ES9121000418450200051332"},
        "required_entities": ["amount", "iban"],
        "confirmed": True,
    },
)
assert not result.flagged
```

The three rule sets compose: a Blue-style three-agent deployment runs all three in parallel, one per agent, aggregating the audit trail across the pipeline.

## Taxonomy of LLM hallucinations

Not all hallucinations are the same. Groundlens is built on a [geometric taxonomy](https://docs.groundlens.dev/theory/hallucination-taxonomy/) ([arXiv:2602.13224](https://arxiv.org/pdf/2602.13224v3)) that classifies hallucinations by their geometric signature in embedding space — which determines whether they are detectable and which scoring method applies.

<div align="center">
<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/taxonomy.png" alt="Hallucination taxonomy on the unit hypersphere" width="480">
<br>
<sub>Every text maps to a point on the hypersphere S<sup>d−1</sup>. The question <b>q</b> and context <b>c</b> define a geodesic arc. Grounded responses (blue) fall inside the plausibility region 𝒫<sub>q</sub>. <b>Type I</b> (purple) stays near q — the response ignored the context. <b>Type II</b> (red) deviates far from both q and c — invented content. <b>Type III</b> (pink) lands inside 𝒫<sub>q</sub> alongside the correct answer — same vocabulary and structure, wrong facts, geometrically indistinguishable.</sub>
</div>
<br>

| Type | What happens | Example | Triage signal |
|---|---|---|---|
| **Type I — Unfaithfulness** | Response ignores the provided source and defaults to the question | RAG system returns an answer from memory instead of from the retrieved document | **SGI** (distance ratio) |
| **Type II — Confabulation** | Response invents content outside the topic's vocabulary | Asked about CRISPR gene editing, the model describes protein-folding correction instead | **DGI** (displacement direction) |
| **Type III — Within-frame error** | Response uses the right vocabulary and structure but gets the facts wrong | "The capital of Australia is Canberra" vs. "The capital of Australia is Sydney" — same frame, wrong city | **Undetectable by geometry** |

**Why Type III is undetectable:** Sentence embeddings encode distributional similarity (vocabulary, syntax, co-occurrence), not truth value. Two responses that share the same words, entities, and syntactic frame land in the same region of embedding space regardless of which one is correct. This is not a limitation of groundlens — it is a property of the distributional hypothesis (Harris, 1954) that constrains every embedding-based method, including NLI (which *inverts* to AUROC 0.311 on TruthfulQA, actively favoring false answers over truthful ones).

**Implications:** Groundlens is **triage** — it ranks the hallucination types that leave geometric traces (Types I and II), which are the most common and most damaging in production. For Type III errors in high-stakes domains (medical, legal, financial), complement groundlens with claim-level fact-checking tools on the outputs that pass geometric triage. See [Complementary Tools for Type III](https://docs.groundlens.dev/theory/confabulation-boundary/#complementary-tools-for-type-iii-detection).

## Scoring methods

Each scoring method targets a specific hallucination type from the taxonomy above.

### SGI (Semantic Grounding Index) — surfaces Type I

When context is available, SGI measures whether the response engaged with the source or stayed anchored to the question:

```
SGI = dist(phi(response), phi(question)) / dist(phi(response), phi(context))
```

| Score | Interpretation |
|---|---|
| SGI > 1.20 | Strong context engagement (high-trust band) |
| 0.95 < SGI < 1.20 | Partial engagement (review recommended) |
| SGI < 0.95 | Weak engagement (low-trust band — possible Type I) |

Thresholds are interpretation aids. For production triage, sort by raw `result.value` and surface the bottom percentile of your batch.

### DGI (Directional Grounding Index) — surfaces Type II

When no context is available, DGI checks whether the question-to-response displacement aligns with a learned "grounded direction":

```
delta = phi(response) - phi(question)
DGI = dot(delta / ||delta||, mu_hat)
```

| Score | Interpretation |
|---|---|
| DGI > 0.30 $^1$ | Aligns with grounded patterns (high-trust band) |
| 0.00 < DGI < 0.30 | Weak alignment (low-trust band — possible Type II) |
| DGI < 0.00 | Opposes grounded direction (highest priority for review) |

$^1$ This score corresponds to a general calibration. In domain-specific calibrations the score can vary.

## Providers and integrations

| Component | Install extra | Description |
|---|---|---|
| **LangGraph** | **`langgraph`** | **Callback handler for agentic pipelines — auto-scores every LLM call, structured traces, HTML triage reports** |
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

## Domains

Groundlens ships a canonical rule set for **banking governance** today (`groundlens_banking_rules` — 20 rules across credit, AML, KYC, fraud, sanctions, concentration, model risk). The architecture is domain-agnostic: `RuleSet` and `ChecklistRule` are composable primitives, and custom rule sets for any in-house governance framework are supported via `RuleSet(rules=(...))` (see [Custom rule sets](#custom-rule-sets) above).

On the roadmap:

- **Legal** — contract review, regulatory filings, litigation discovery rationale evaluation
- **Insurance** — claim adjudication, underwriting, fraud investigation rationale evaluation
- **Healthcare** — clinical decision support, prior authorization, coding rationale evaluation

The geometric layer (SGI/DGI) is already domain-agnostic — `compute_dgi` accepts a `reference_csv` argument for domain calibration. The rule layer's generalization is the active area of work.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Public API (evaluate)                        │
├────────────────────┬────────────────────────────────────────────┤
│  Geometric layer   │            Rule-based layer                │
├────────────────────┼──────────────┬──────────────┬──────────────┤
│ SGI │ DGI          │    rules     │    audit     │  compliance  │
│ (geometry +        │  (deterministic │  (SHA-256  │ (mapping to  │
│  embeddings)       │   pattern      │  hash chain │  SR 26-2,    │
│                    │   matching)    │   log)     │  EU AI Act,  │
│                    │                │            │  NIST RMF)   │
├────────────────────┴──────────────┴──────────────┴──────────────┤
│                  groundlens.agents                              │
│  routing_rules   │   rag_rules    │   specialized_agent_rules   │
│  (intent class.) │ (RAG / informa-│  (entity capture +          │
│                  │  tional agent) │   tool-use execution)       │
├─────────────────────────────────────────────────────────────────┤
│        sentence-transformers (all-MiniLM-L6-v2)                 │
└─────────────────────────────────────────────────────────────────┘
         ▲                       ▲
         │                       │
  ┌──────┴──────┐       ┌────────┴─────────┐
  │  Providers  │       │   Integrations   │
  │  (OpenAI,   │       │   (LangGraph,    │
  │  Anthropic, │       │   LangChain,     │
  │  Google)    │       │   CrewAI, SK,    │
  │             │       │   AutoGen)       │
  └─────────────┘       └──────────────────┘
```

Two complementary triage layers — geometric (SGI/DGI, sub-second, ranks the bottom percentile by grounding signal) and rule-based (per-rule audit trail with regulatory citations). Per-agent factories under `groundlens.agents` adapt the rule-based layer to the three agent classes that appear in most production deployments. All deterministic. All auditable. No second LLM in any of them.

See [AGENTS.md](AGENTS.md) for detailed file-by-file documentation. See [CLAUDE.md](CLAUDE.md) for AI-assisted development guidelines.

## Research

groundlens implements the methods described in four research papers:

1. **Semantic Grounding Index (SGI)**
   Marin, J. (2025). *Semantic Grounding Index for LLM Hallucination Detection.*
   [arXiv:2512.13771](https://arxiv.org/abs/2512.13771)

2. **Hallucinations Taxonomy | Directional Grounding Index (DGI)**
   Marin, J. (2026). *A Geometric Taxonomy of Hallucinations in Large Language Models.*
   [arXiv:2602.13224](https://arxiv.org/pdf/2602.13224v3)

3. **Mechanistic Interpretability**
   Marin, J. (2026). *Rotational Dynamics of Factual Constraint Processing in Large Language Models.*
   [arXiv:2603.13259](https://arxiv.org/abs/2603.13259)

4. **Multi-source rule provenance for banking governance** *(preprint, draft available on request)*
   Marin, J. (2026). *Defendable Rules for LLM Rationale Evaluation in Banking Governance: A Multi-Source Provenance Framework.*
   Underpins the `groundlens_banking_rules` reference set: 20 rules triangulated across peer-reviewed NLP literature, tier-1 bank public reports, banking regulator whitepapers, cross-industry frameworks, and financial-domain NLP benchmarks.
