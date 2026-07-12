<div align="center">
<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/logo.png" alt="groundlens" width="150">

# Groundlens: the deterministic first stage for RAG and agent loops. It decides what your LLM judge has to look at.
</div>

<div align="center">

[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![Version](https://img.shields.io/badge/version-2026.7.6-orange?style=flat-square)](https://github.com/groundlens-dev/groundlens/releases)
[![License: Apache](https://img.shields.io/badge/license-Apache%202-g?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/groundlens-dev/groundlens?style=flat-square&label=OpenSSF%20Scorecard)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13390/badge)](https://www.bestpractices.dev/projects/13390)

[Documentation](https://docs.groundlens.dev) · [Benchmarks](#benchmarks) · [Research](#research) · [Examples](examples/) · [Vision](VISION.md) · [Contributing](CONTRIBUTING.md)

</div>

---

The standard way to check an LLM's output is a second LLM as judge, paid on every output: non-deterministic at temperature 0, a free-text opinion with no citation, priced per call. Groundlens is the deterministic **first stage** that runs in front of that judge. Two deterministic layers, geometric scoring and citation-backed rules, clear the clearly grounded answers and catch the clearly ungrounded ones, sub-second, with no LLM in the scoring path, so the expensive judge runs only on what Groundlens escalates. It settles whether an answer engaged its source. A plausible wrong fact stated in the right frame is provably invisible to geometry, and Groundlens escalates it to your second stage. Built for RAG systems and agent loops in regulated industries.

> **Use Groundlens in your editor:** the [**Groundlens MCP server**](https://github.com/groundlens-dev/groundlens-mcp) adds deterministic hallucination checks to Claude, Cursor, and VS Code — [one-click install ›](https://github.com/groundlens-dev/groundlens-mcp#one-click-install)

## See it run

<div align="center">
<img src="examples/groundlens_check.gif" alt="Groundlens MCP: a grounding CHECK printed live under every answer inside Claude" width="100%">
<br>
<em>The Groundlens MCP inside Claude: a deterministic CHECK under every answer. Question 4 asks for a figure the report never gives — Claude declines, and the check catches it anyway: provenance, not truth.</em>
</div>

**Live demo:** [groundlens-demo.hf.space](https://groundlens-demo.hf.space)

## Two deterministic layers, one audit packet

Groundlens verifies agent outputs with two layers stitched into one audit packet. Neither alone is enough; the combination is what a Model Risk Committee, an internal audit, or an external supervisor accepts.

- **Geometric scoring** (SGI, DGI) — continuous, calibrated, sub-second. Captures semantic drift that rules miss, and produces a ranking signal for prioritized review queues at production scale.
- **Rule-based audit** — per-rule pass/fail with a citation to the academic, industrial, or regulatory source that motivated the check. Byte-identical reproducibility across years and runs.
- **Bring your own embeddings** — inject any encoder via `encoder=` (or `set_default_encoder(...)` once). Score with a hosted embedding API, an in-house model, or precomputed vectors — and run SGI/DGI **without torch**.

Groundlens is **Stage 1**: it runs first, deterministically, on every output. The expensive LLM-as-judge (or a human) is **Stage 2**, and it runs only on what Stage 1 escalates.

| Stage | Component | What it answers | Limit alone |
|---|---|---|---|
| **Stage 1** | Geometric scoring (SGI, DGI) | "How far is this response from the grounded reference distribution, on a continuous scale?" | No human-readable trail per response; can't say *why* it drifted |
| **Stage 1** | Rule-based audit | "Which specific fact, citation, or procedural element is missing or fabricated, and on what authority?" | Binary checks; doesn't capture semantic drift outside the rule patterns |
| Stage 2 (downstream) | LLM-as-judge or human | "Does this look right, and is the fact true?" | Non-deterministic at T=0; free-text reasons, no citations; ~$300/M outputs. Run it only on what Stage 1 escalates. |

Stage 1 gives you two things Stage 2 cannot afford at scale: a **continuous score** to triage the bottom 5% of a million daily outputs, and a **citation-backed audit trail** an auditor can reproduce two years from now, tied together by a hash-chained log. What Stage 1 cannot settle, a plausible in-register factual error, it escalates to Stage 2. Without Stage 1 you run the expensive judge on everything; without Stage 2 you cannot settle facts.

## What Groundlens detects

The geometric layer rests on three published papers that state exactly which hallucinations angular geometry can and cannot separate. A precise statement of scope is the most important thing this README can give a Head of Model Risk reading it for the first time.

| Hallucination type | What it looks like | Detectable by Groundlens? |
|---|---|---|
| **Type I — Query-proximate unfaithfulness** | Response ignores the retrieved context and defaults to the question's topic | **SGI**, when context is available. Validated on HaluEval QA (AUROC ≈ 0.81 averaged across five encoders) |
| **Type II — Confabulation outside plausibility region** | Response imports vocabulary from an adjacent register (e.g., describing CRISPR using protein-folding terms) | **DGI** with domain calibration. Validated on a 212-pair human-confabulated dataset (87.8% on declarative-knowledge domains); NLI on the same pairs reaches only 57.5% |
| **Type III — Factual error within the same frame** | Wrong number, wrong name, wrong date — same vocabulary, same topic, same syntax as the correct answer | **NOT** detectable by angular geometry. Documented as a *negative result* on TruthfulQA, AUROC = 0.478 — *below chance*. For Type III, escalate to your second stage: an LLM judge, domain NLI, KG verification, or a human. No embedding method separates this class |


References: Marin (2025) [SGI, arXiv:2512.13771](https://arxiv.org/abs/2512.13771) · Marin (2026) [Geometric Taxonomy + DGI, arXiv:2602.13224](https://arxiv.org/abs/2602.13224) · Marin (2026) [Rotational Dynamics, arXiv:2603.13259](https://arxiv.org/abs/2603.13259).

**For regulated-industry deployments:** Type III is the most critical class in banking, healthcare, and legal — a wrong figure in a financial summary, a wrong dose in a clinical recommendation. Groundlens does *not* claim to catch those geometrically. The rule-based layer (`groundlens.rules`) is designed exactly for the policy and citation checks that Type III demands. The rule-based layer catches the Type III cases a policy or citation check can express; the residue, a plausible wrong figure that passes every rule, is escalated to a second-stage judge or human. SGI/DGI for the Type I/II screen, rules plus that escalation for Type III, is what passes a Model Risk Committee review.

## Benchmarks

Groundlens is measured against published benchmarks and against an independent one. The point of this section is not a single headline number — it is to show, precisely, where geometry wins and where it does not.

### Validated against Google DeepMind's FACTS

FACTS Grounding (Google DeepMind) measures whether an answer stays faithful to the document it was given — scored by an ensemble of frontier LLM judges. A precise instrument, and an expensive one: fit to rank models on a leaderboard, not to check every response in production.

We ran Groundlens against FACTS' own public examples to ask how much of that judgment is recoverable from geometry alone — no LLM in the loop. The single grounding verdict splits in two:

| Question | Geometry alone |
|---|---|
| **Attribution** — did this answer come from *this* document, and not another? | AUROC ≈ 0.95. Deterministic, sub-second, no LLM. |
| **Faithfulness** — is every individual claim supported? | A filter, not a verdict: as a first pass it catches ≈ 85% of the answers the judge would flag, leaving a smaller set for expensive review. |

The point is not that geometry replaces the judge. It is that one half of grounding — where an answer came from — is nearly free, and can clear the clearly-grounded answers and catch most of the ungrounded ones before a single LLM call.

*Method: a single-judge proxy for FACTS' three-model ensemble, over the public v2 examples; short answers under-scored. Reproduce it in the repo notebook]*:[`notebooks/groundlens_x_facts_grounding.ipynb`](notebooks/groundlens_x_facts_grounding.ipynb).

<div align="center">
<img src="examples/anim_histogram.gif" alt="Every FACTS example placed by its grounding geometry" width="100%">
<br>
<em>Every FACTS example placed by its grounding geometry; grounded and ungrounded separate before any judge is asked. Labels decided by Claude Sonnet 5.</em>
</div>

### Published results

From the SGI and DGI papers. Every row is reproducible from the linked paper's released code.

| Benchmark | Task | Metric | Baseline | Note |
|---|---|---|---|---|
| **HaluEval QA** (n = 10,000) | Type I, context available | **SGI AUROC 0.805** (mean over 5 encoders, range 0.78–0.82) | NLI 0.748 · cosine similarity 0.941 | On LLM-generated hallucinations, correct and wrong answers sit far apart, so even cosine separates. SGI's value is decomposition and the harder cases below, not this number. |
| **Human-confabulated** (212 pairs, 9 domains) | Type II, realistic errors | **DGI 87.8%** detection on declarative-knowledge domains; 56.9% on template domains | NLI 57.5% (AUROC 0.536, ≈ chance) | The realistic case. Human confabulations sit *close* to the grounded answer (cosine 0.72–0.92), where surface methods collapse and directional geometry still separates. |
| **TruthfulQA** (n = 800) | Type III, same-frame factual error | **AUROC 0.478 — below chance** | — | Published *negative result*. Angular geometry measures topical engagement, not factual truth. Escalate Type III to your second stage: a judge, KG verification, or a human. |

Two findings. First, geometry is not magic: on same-topic factual errors it is below chance, and it says so. Second, geometry earns its place exactly where the cheap surface baselines fail — the human-confabulated case that resembles real deployments, where NLI drops to chance and directional grounding does not. Cosine similarity win (0.941) when the error sits far from the truth — the HaluEval dataset case — and collapse when it sits close, the human-confabulation case that resembles real deployments (NLI drops to 0.536, chance). A production detector has to work in the second regime. That is what directional and ratio geometry are for.

Domain calibration moves the operating point: generic thresholds sit near AUROC 0.76; with 20–50 verified-grounded pairs from your own domain the reported range rises toward 0.90–0.99 on labelled corpora. Calibration, not the default threshold, is the deployment configuration — see [Calibrating SGI and DGI](#calibrating-sgi-and-dgi).

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

## Plain-language checks (`check`)

A raw score and a boolean flag are the right output for a pipeline and the wrong output for a person. `check()` turns any SGI, DGI, or `evaluate()` result into one plain-language reading under the headline **CHECK**. It is the single source of truth for wording — the docs and the [MCP servers](https://github.com/groundlens-dev/groundlens-mcp) render from it, so the phrasing is identical everywhere.

```python
from groundlens import compute_sgi, check

sgi = compute_sgi(question=question, context=context, response=response)
print(check(sgi).render())
# CHECK: Not supported by the document (Semantic Grounding Index - SGI=0.83)
# The answer stays closer to the question than to the source, so it may not
# come from the document. Check it before trusting it.
```

Context-free DGI reads the same way, and states plainly that it had no source to check against:

```python
from groundlens import compute_dgi, check

dgi = compute_dgi(question=question, response=response)
print(check(dgi).render())
# CHECK: Looks grounded (Directional Grounding Index - DGI=0.41)
# The answer moves the way well-grounded answers usually do.
# No source given — judged by the shape of the answer.
```

The check **level** (`ok` / `review` / `risk`, on `check(...).level`) comes only from the calibrated thresholds. The label and message are jargon-free — "grounding" and "hallucination" never appear in what the user reads. The raw components — `q_dist` / `ctx_dist` for SGI, the displacement `magnitude` for DGI — are surfaced on `check(...).detail` for anyone who wants them, not used to invent uncalibrated cut-points.

| Metric | `check` labels | Level from |
|---|---|---|
| **SGI** | Supported by the document · Partly supported · Not supported by the document | SGI ≥ 1.20 / ≥ 0.95 / below |
| **DGI** | Looks grounded · Partly grounded · Not grounded | DGI ≥ 0.30 / ≥ 0.0 / below |

## Custom encoders / no-torch

By default Groundlens loads a `sentence-transformers` model on first use. You can supply your own embedding function instead — to reuse a hosted embedding API, an in-house model, or precomputed vectors, and to run SGI/DGI **without installing torch** (the custom-encoder path never imports `sentence-transformers`).

An encoder is *a callable taking `list[str]` and returning an `(n, d)` array*. Pass it per call, or register it once:

```python
import groundlens
# Per-call: e.g. a SentenceTransformer's bound .encode, or any function.
from sentence_transformers import SentenceTransformer
encoder = SentenceTransformer("all-MiniLM-L6-v2").encode
groundlens.compute_sgi(question="...", context="...", response="...", encoder=encoder)
groundlens.compute_dgi(question="...", response="...", encoder=encoder)

# Process-global: applies to every call, no monkeypatching.
groundlens.set_default_encoder(encoder)
groundlens.compute_dgi(question="...", response="...")
groundlens.set_default_encoder(None)  # restore the default path
```

The bundled SGI/DGI thresholds and DGI `mu_hat` are calibrated for the default encoder. When you switch encoders, re-fit with `groundlens.fit_thresholds(...)` (cutoffs) and `groundlens.calibrate(...)` (reference direction) — both accept the same `encoder=`. See the [Custom Encoders guide](https://docs.groundlens.dev/guides/custom-encoders/).

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

## Bootstrap your calibration set (`DGI.propose_labels`)

Calibrating DGI on a new deployment needs 20–50 verified-grounded `(question, response)` pairs. Curating that corpus from scratch is the practical bottleneck most teams hit first. `DGI.propose_labels` is the active-learning loop that breaks it.

> **Three sentences.** You give DGI a few correct examples from your FAQ. It asks an LLM to write wrong versions of those answers in five different ways, then shows you the ones it found hardest to classify. Your labels make DGI sharper. Repeat until AUROC plateaus.

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

For other agent frameworks (LangGraph, CrewAI, Semantic Kernel, AutoGen, custom), the integration is identical: call `compute_sgi` / `DGI.score` / `ruleset.evaluate` after every generation and persist via `groundlens.audit`. See [docs/integrations](https://docs.groundlens.dev/integrations/) for framework-specific snippets. For editor and IDE workflows, the [Groundlens MCP server](https://github.com/groundlens-dev/groundlens-mcp) exposes the same checks to Claude, Cursor, and VS Code.

## Architecture

Groundlens is two layers: **Score** (continuous, geometric) and **Rules** (deterministic, citable). Triage is the combination. Calibration data is what makes both layers useful — `propose_labels` is the active-learning helper that produces it.

![Topology of groundlens (Score + Rules + propose_labels)](docs/assets/groundlens_topology.png)

Full component and lifecycle tables (modules, inputs, outputs, calibration, compliance mapping) live in the docs to keep this README readable: **[docs.groundlens.dev/architecture](https://docs.groundlens.dev/architecture/)**. The one-line summary: continuous geometric score for ranking, per-rule audit trail with citations, hash-chained log for reproducibility, compliance mapping for the model-risk packet, with no LLM in the scoring path. Your second-stage judge or human runs only on what Groundlens escalates.

## Research

The methods Groundlens implements are documented in four research papers:

1. **Semantic Grounding Index** — Marin (2025). [arXiv:2512.13771](https://arxiv.org/abs/2512.13771). Ratio-based geometric grounding for RAG.
2. **A Geometric Taxonomy of Hallucinations** — Marin (2026). [arXiv:2602.13224](https://arxiv.org/abs/2602.13224). Type I (off-context) vs Type II (in-context fabrication); DGI as the Type II detector.
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

Apache-2.0. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [CLAUDE.md](CLAUDE.md), [AGENTS.md](AGENTS.md).
