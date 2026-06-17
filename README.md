<div align="center">
<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/Logo_groundlens_new-05.png" alt="groundlens" width="250">

# Groundlens
## Verifiable agent triage
</div>



<div align="center">

[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![Version](https://img.shields.io/badge/version-2026.6.17-orange?style=flat-square)](https://github.com/groundlens-dev/groundlens/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](https://opensource.org/licenses/MIT)

[Documentation](https://docs.groundlens.dev) · [Research](#research) · [Examples](examples/) · [Vision](VISION.md) · [Contributing](CONTRIBUTING.md)

</div>

---

Modern AI deployments run **agent pipelines**, not single models. Routing decides intent. RAG retrieves and answers. Specialized agents capture entities and execute operations. Each layer can fail differently, and the standard verification approach — a second LLM as judge — does not survive a model risk review.

Groundlens verifies agent outputs with two deterministic layers stitched into one audit packet:

- **Geometric scoring** (SGI, DGI) — continuous, calibrated, sub-second. Captures semantic drift that rules miss, and produces a ranking signal usable for prioritized review queues at production scale.
- **Rule-based audit** — per-rule pass/fail with a citation to the academic, industrial, or regulatory source that motivated the check. Byte-identical reproducibility across years and runs.

The combination is what a Model Risk Committee, an internal audit, or an external supervisor accepts. Neither layer alone is enough.

## Why geometry **and** rules

Each layer answers a different question. Both questions get asked in a real audit.

| Layer | What it answers | Limit when used alone |
|---|---|---|
| LLM-as-judge | "Does this response look right semantically?" | Non-deterministic at T=0; free-text reasons, no citations; ~$300/M outputs at gpt-4o-mini scale |
| Geometric scoring | "How far is this response from the grounded reference distribution, on a continuous scale?" | No human-readable trail per response; can't say *why* it drifted |
| Rule-based audit | "Which specific fact, citation, or procedural element is missing or fabricated, and on what authority do we say so?" | Binary verdicts; doesn't capture semantic drift outside the rule patterns |

Rules give you the **citation-backed audit trail** an auditor needs to reproduce a decision two years from now. Geometry gives you the **continuous score** an operations team needs to triage the bottom 5% of a million daily outputs. Without rules, you can't defend the decision. Without geometry, you can't scale the review. Groundlens ships both, and a hash-chained audit log that ties them together.

## Quick start

```bash
pip install groundlens
```

**RAG triage — SGI + customer-support rules.** The typical FAQ-RAG archetype: question, retrieved context, generated response.

```python
from groundlens import compute_sgi
from groundlens.agents import customer_support_rules

question = "What is the Bizum daily limit?"
context  = "The daily Bizum transfer limit is 1,000 EUR per transaction and 2,000 EUR per day."
response = "The Bizum daily limit is 500 EUR per transaction. Premium clients have 10,000 EUR."

sgi   = compute_sgi(question=question, context=context, response=response)
rules = customer_support_rules().evaluate(
    question=question, response=response, context=context,
)

print(sgi.normalized)              # 0.92  — closer to grounded reference, but
print(rules.flagged)               # True  — rule csr.no_invented_numbers triggered
print(rules.audit_explanation)     # full per-rule trail with citations
```

**Closed-context triage — DGI + rules.** When no retrieval context is available (chat, agent self-verification). DGI compares the response's semantic direction against a domain-calibrated `mu_hat`. Pass `rag=False` to `customer_support_rules` so the rule set drops the groundedness sub-score (nothing to ground against).

```python
from groundlens import DGI
from groundlens.agents import customer_support_rules

# Calibrate DGI with verified (question, response) pairs from your domain.
# The reference distribution is what "grounded" means for your specific deployment.
dgi = DGI()
dgi.calibrate(pairs=[(q, r) for q, r in verified_grounded_logs])  # 20-50 pairs

dgi_score = dgi.score(question, response)
rules     = customer_support_rules(rag=False).evaluate(
    question=question, response=response,
)

flagged = dgi_score.flagged or rules.flagged
```

The flag combiner is a deployer decision: `OR` for recall (more flags to human review), `AND` for precision, or a weighted geometric mean.

## Built-in rule sets

Every rule carries a citation to its source — academic paper, industry whitepaper, or regulatory clause. Pick the rule set that matches the agent class you are triaging.

From release **2026.6.13** the rule-set API follows a single convention: **the archetype is the function name, the deployment dimensions are keyword arguments**. See [ADR 0001](docs/adr/0001-rule-set-architecture.md) for the rationale.

| Rule set | Use it for | Sub-scores | Rules |
|---|---|---|---|
| [`routing_rules(domain="general")`](src/groundlens/agents/routing.py) | Intent-classification agents (multi-class routing, fallback, clarify) | intent_clarity, classification_confidence, fallback_appropriateness, disambiguation_quality | 10 |
| [`customer_support_rules(rag=True, domain="general", language="en")`](src/groundlens/agents/customer_support.py) | Informational customer-facing agents (FAQ-RAG and chat-without-context) | groundedness, completeness, no_overreach (RAG) / completeness, no_overreach (no-RAG) | 7 / 4 |
| [`decision_rationale_rules(domain="finance", regulations=())`](src/groundlens/rules.py) | Decision rationales (credit, AML, KYC, fraud, sanctions) | groundedness, completeness, calibration, traceability, robustness | 20 |
| [`specialized_agent_rules(domain="general", tools=())`](src/groundlens/agents/specialized.py) | Tool-using / execution agents (entity capture, transaction execution) | entity_groundedness, entity_completeness, entity_calibration, execution_readiness | 9 |
| [`banking_rules()`](src/groundlens/rules.py) (legacy) | Mechanical-enforcement skeleton from De La Chica & Martí-González (2026) | spec, expl, bshift | 22 |

**Deprecated, kept as aliases for one or more releases:**

- `customer_support_rag_rules()` → use `customer_support_rules(rag=True)`.
- `groundlens_banking_rules()` → use `decision_rationale_rules(domain="finance")`.
- `rag_rules(domain="banking" | "customer_support")` → call the canonical archetype factory directly. The dispatcher emits a `DeprecationWarning`.

For legal, insurance, healthcare, or any in-house governance framework, extend an existing factory (`domain="..."` slot) or write your own (see below).

## Bootstrap your calibration set (`DGI.propose_labels`)

Calibrating DGI on a new deployment needs 20–50 verified-grounded `(question, response)` pairs. Curating that corpus from scratch is the practical bottleneck most teams hit first. `DGI.propose_labels` is the active-learning loop that breaks it.

> **Three frases.** You give DGI a few correct examples from your FAQ. It asks an LLM to write wrong versions of those answers in five different ways, then shows you the ones it found hardest to classify. Your labels make DGI sharper. Repeat until AUROC plateaus.

```python
from groundlens import DGI, SeedExample

def my_llm(prompt: str) -> str:
    ...  # your OpenAI / Anthropic / local LLM wrapper

dgi = DGI()  # starts from the bundled cross-domain calibration

seeds = [
    SeedExample(
        context="Bizum permite enviar dinero ... limite de 1.000 EUR por transaccion.",
        question="Cual es el limite por transaccion de Bizum?",
        grounded="El limite por transaccion de Bizum es de 1.000 EUR.",
    ),
    # 10-20 more SeedExample triples from your FAQ
]

batch = dgi.propose_labels(
    seeds=seeds,
    llm_generate=my_llm,
    n_candidates=50,     # default; ≈5 min at 4 s/call
    n_to_label=10,       # default; how many the reviewer sees
)

# Hand the Markdown checklist to a human reviewer (two reviewers reconciled is best).
print(batch.review_template)

# Once labelled, feed the grounded subset back to calibrate.
dgi.calibrate(pairs=labelled_grounded_pairs)
```

`SeedExample` bundles `context`, `question` and `grounded` so the confabulation prompt is always coherent — the previous `(faq_corpus, seed_pairs)` shape paired them randomly and produced incoherent candidates. The five built-in strategies (`redefinition`, `mechanism_inversion`, `entity_composition`, `polysemy`, `template_filling`) come from [`groundlens-dev/grounding-benchmark`](https://github.com/groundlens-dev/grounding-benchmark) (CC BY 4.0); custom strategies via `(name, prompt_template)` tuples.

`propose_labels` does NOT label and does NOT calibrate — the human assigns the labels, the loop is non-circular by design. SGI has no calibration parameter, so this applies only to DGI.

Full step-by-step guide with troubleshooting: **[docs/guides/active-learning.md](docs/guides/active-learning.md)**.

## Calibrating SGI and DGI

Both geometric scores need domain calibration. Generic thresholds and the bundled `mu_hat` are starting points, not deployment configuration. The published SGI and DGI papers report AUROC ~0.76 generic vs **0.90–0.99** with domain calibration on labelled banking corpora.

**SGI** — threshold over the normalized score:

```python
import numpy as np
from groundlens import compute_sgi

reference = [(q, ctx, r) for q, ctx, r in verified_grounded_logs]   # 20-50 triples
scores    = np.array([
    compute_sgi(question=q, context=ctx, response=r).normalized
    for q, ctx, r in reference
])
SGI_THRESHOLD = float(np.percentile(scores, 20))   # or p25, p10 — your operational call
```

**DGI** — calibrate `mu_hat` with `(question, response)` pairs and threshold the same way:

```python
from groundlens import DGI

dgi = DGI()
dgi.calibrate(pairs=[(q, r) for q, r in verified_grounded_logs])

scores        = np.array([dgi.score(q, r).normalized for q, r in verified_grounded_logs])
DGI_THRESHOLD = float(np.percentile(scores, 20))
```

The calibration set need not be large (20–50 verified-grounded pairs is enough for a useful signal). It must be **verified grounded**: the geometry compares every new response against this reference distribution. Garbage in, garbage threshold.

Full guide with AUROC calibration, drift monitoring, and recalibration triggers: [docs/guides/domain-calibration.md](https://docs.groundlens.dev/guides/domain-calibration/).

## Build your own rule set

The rule engine is intentionally small. `RuleSet` and `ChecklistRule` are composable primitives — you write pure-Python `check` functions and group them under sub-score categories with a flag predicate. Every rule must carry a `citation`; that field is what survives an audit.

```python
from groundlens import ChecklistRule, RuleEvidence, RuleSet


def check_cites_clause(question, response, context, metadata):
    matched = "clause" in response.lower() or "§" in response
    return RuleEvidence(
        matched=matched,
        span="clause/§",
        explanation="rationale cites a specific contract clause",
    )


def flag_predicate(sub_scores):
    # Non-compensatory: safety dimensions don't average with UX dimensions.
    return sub_scores.get("groundedness", 0.0) < 0.5


legal_ruleset = RuleSet(
    name="legal_contract_review_v1",
    rules=(
        ChecklistRule(
            id="legal.cites_clause",
            description="rationale cites a specific contract clause",
            weight=0.60,
            sub_score="traceability",
            check=check_cites_clause,
            citation="EU AI Act 2024/1689 Art. 13(3)(b)(iv) — explain output capability",
        ),
        # ... more rules
    ),
    sub_scores=("groundedness", "traceability"),
    flag_predicate=flag_predicate,
)
```

Full 4-step recipe with anatomy, patterns, and common pitfalls: **[docs/guides/custom-rule-sets.md](docs/guides/custom-rule-sets.md)**.

Runnable end-to-end legal example: **[examples/custom_rules.py](examples/custom_rules.py)**.

## End-to-end pipeline (LangChain + Groundlens)

A realistic production pattern. LangChain handles retrieval and generation; Groundlens triages every output with SGI + rules, persists a hash-chained audit log, and routes flagged responses to human review before they reach the customer.

```python
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from groundlens import compute_sgi
from groundlens.agents import customer_support_rules
from groundlens.audit import open_log

# 1. Standard LangChain RAG -----------------------------------------------
embeddings  = OpenAIEmbeddings()
vectorstore = FAISS.from_texts(faq_corpus, embeddings)
retriever   = vectorstore.as_retriever(search_kwargs={"k": 1})
llm         = ChatOpenAI(model="gpt-4o-mini", temperature=0)

prompt = ChatPromptTemplate.from_template(
    "Answer the question using only the context.\n\n"
    "Context: {context}\n\nQuestion: {question}"
)

rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | prompt | llm | StrOutputParser()
)

# 2. Groundlens triage on every response ----------------------------------
ruleset       = customer_support_rules()
SGI_THRESHOLD = 0.85   # calibrated from your grounded reference distribution

def triage(question: str) -> dict:
    docs     = retriever.invoke(question)
    context  = docs[0].page_content
    response = rag_chain.invoke(question)

    sgi   = compute_sgi(question=question, context=context, response=response)
    audit = ruleset.evaluate(question=question, response=response, context=context)

    flagged = sgi.normalized < SGI_THRESHOLD or audit.flagged
    return {
        "response": response,
        "sgi": sgi.normalized,
        "rules_quality": audit.quality,
        "flagged": flagged,
        "audit": audit.audit_explanation,
    }

# 3. Persistent audit log with SHA-256 hash chain -------------------------
with open_log("triage.db") as log:
    for question in incoming_questions:
        r = triage(question)
        log.append(
            question=question,
            response=r["response"],
            sgi=r["sgi"],
            rules_quality=r["rules_quality"],
            flagged=r["flagged"],
            audit=r["audit"],
        )
        if r["flagged"]:
            route_to_human_review(r)
        else:
            return_to_customer(r["response"])
```

The audit log is hash-chained: a supervisor can replay any decision byte-for-byte two years from now and verify the chain has not been altered. That is what SR 26-2, EU AI Act Art. 13, and NIST AI RMF reproducibility requirements look like in practice.

For other agent frameworks (LangGraph, CrewAI, Semantic Kernel, AutoGen, custom), the integration is identical: call `compute_sgi` / `DGI.score` / `ruleset.evaluate` after every generation and persist via `groundlens.audit`. See [docs/integrations](https://docs.groundlens.dev/integrations/) for framework-specific snippets.

## Architecture

Groundlens is two layers: **Score** (continuous, geometric) and **Rules** (deterministic, citable). Triage is the combination. Calibration data is what makes both layers useful — `propose_labels` is the active-learning helper that produces it.

![Topology of groundlens (Score + Rules + propose_labels)](docs/assets/groundlens_topology.png)

### Table 1 — Layers and what's in each

| Layer | Module | Inputs | Output | Calibrable? | Bundled defaults | Custom extension |
|---|---|---|---|---|---|---|
| **Score — geometry** | `groundlens.sgi`, `groundlens.dgi` | `(question, response[, context])` + sentence-transformer embedding | continuous `normalized` ∈ ℝ, `flagged` ∈ {True, False} | **DGI yes** (via `mu_hat`). SGI no — geometric ratio with no parameter. | bundled `reference_pairs.csv` (212 cross-domain pairs from `grounding-benchmark`) | `DGI.calibrate(pairs=…)` or `reference_csv=…` |
| **Score — encoder** | `groundlens._internal.embeddings` | text | unit-norm vector | n/a | `all-MiniLM-L6-v2` for English, `MULTILINGUAL_MINI` / `MULTILINGUAL_E5` for multilingual | any sentence-transformers model |
| **Rules** | `groundlens.rules`, `groundlens.agents.*` | `(question, response, context, metadata)` | per-rule pass/fail with citation + sub-scores + `audit_explanation` | n/a (deterministic) | `routing_rules`, `customer_support_rules(rag=…)`, `specialized_agent_rules`, `decision_rationale_rules(domain=…, regulations=…)` | `RuleSet(rules=(ChecklistRule(...), ...))` |
| **Audit** | `groundlens.audit` | every triage output | SHA-256 hash-chained sqlite log | n/a | `open_log("triage.db")` | append-only, replay-verifiable |
| **Compliance mapping** | `groundlens.compliance` | rule IDs | clause IDs (SR 26-2, EU AI Act, NIST AI RMF) | n/a | included for built-in rule sets | extend in your own rule set's `citation` field |

### Table 2 — Lifecycle: from zero calibration to production triage

| # | Step | What you do | Groundlens API | Output |
|---|---|---|---|---|
| 0 | **Seed** | Hand-curate 10–50 verified-grounded `(question, response)` pairs from your domain | — | seed CSV / list |
| 1 | **Bootstrap** ⭐ NEW | Active-learning loop generates candidates, scores them with current DGI, returns most uncertain for human review | `DGI.propose_labels(faq_corpus=…, seed_pairs=…, llm_generate=…)` | `PropositionBatch` (items, `review_template` Markdown) |
| 2 | **Label** | Two human reviewers label the batch independently, reconcile disagreements | external (the review template is the prompt) | labelled set: `{grounded, fabricated, out_of_scope}` |
| 3 | **Calibrate** | Feed the labelled grounded subset back to DGI; threshold the score distribution | `DGI.calibrate(pairs=…)` then `np.percentile(scores, 20)` | calibrated `mu_hat` + threshold |
| 4 | **Triage** | For every agent output, compute score + run the relevant rule set | `compute_sgi(...)` / `DGI.score(...)`, `ruleset.evaluate(...)` | continuous score + per-rule trail |
| 5 | **Audit** | Persist every triage to the hash-chained log | `groundlens.audit.open_log("triage.db")` | replayable SR 26-2 / EU AI Act packet |
| 6 | **Recalibrate** | When drift exceeds threshold, return to step 1 with the recent traffic as `faq_corpus` | `DGI.propose_labels(...)` again | next-round batch |

The loop is intentionally non-circular: DGI scores propose ordering, humans own labels, calibrated DGI scores production traffic. Continuous geometric score for ranking. Per-rule audit trail with citations. Hash-chained log for reproducibility. Compliance mapping for the model risk packet. No second LLM in any of them.

## Research

The methods Groundlens implements are documented in four research papers:

1. **Semantic Grounding Index** — Marin (2025). [arXiv:2512.13771](https://arxiv.org/abs/2512.13771). Ratio-based geometric grounding for RAG.
2. **A Geometric Taxonomy of Hallucinations** — Marin (2026). [arXiv:2602.13224](https://arxiv.org/pdf/2602.13224v3). Type I (off-context) vs Type II (in-context fabrication); DGI as the Type II detector.
3. **Rotational Dynamics of Factual Constraint Processing** — Marin (2026). [arXiv:2603.13259](https://arxiv.org/abs/2603.13259). Mechanistic interpretability of how transformers reject wrong answers.
4. **Defendable Rules for LLM Rationale Evaluation in Banking Governance: A Multi-Source Provenance Framework** — Marin (2026). *Preprint, draft available on request.* Underpins `decision_rationale_rules(domain="finance")`: 20 rules triangulated across peer-reviewed NLP literature, banking-regulator whitepapers, tier-1 bank public reports, cross-industry frameworks, and financial-domain NLP benchmarks.

## Compliance mapping

Built-in mapping from Groundlens components to specific regulatory clauses:

- **SR 26-2** (Federal Reserve, April 2026 — supersedes SR 11-7) — [docs/guides/sr-11-7.md](docs/guides/sr-11-7.md)
- **EU AI Act 2024/1689** — [docs/guides/eu-ai-act.md](docs/guides/eu-ai-act.md)
- **NIST AI RMF 1.0** — [docs/guides/nist-ai-rmf.md](docs/guides/nist-ai-rmf.md)
- **Banking deployment guide** — [docs/guides/banking-deployment.md](docs/guides/banking-deployment.md)

## Installation

```bash
pip install groundlens                     # core
pip install "groundlens[openai]"           # OpenAI provider
pip install "groundlens[anthropic]"        # Anthropic provider
pip install "groundlens[langchain]"        # LangChain integration
pip install "groundlens[langgraph]"        # LangGraph per-node scoring
pip install "groundlens[all]"              # everything
```

Requirements: Python 3.10+, numpy, sentence-transformers.

## License

MIT. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [CLAUDE.md](CLAUDE.md), [AGENTS.md](AGENTS.md).
