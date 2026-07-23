<div align="center">
<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/logo.png" alt="groundlens" width="150">

# Groundlens

### Check whether an LLM's answer actually came from its source. Fast, deterministic, no second LLM.

[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![Version](https://img.shields.io/badge/version-2026.7.14-orange?style=flat-square)](https://github.com/groundlens-dev/groundlens/releases)
[![License: Apache](https://img.shields.io/badge/license-Apache%202-green?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/groundlens-dev/groundlens?style=flat-square&label=OpenSSF%20Scorecard)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)

<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/groundlens_claude_mcp.gif" alt="A grounding CHECK printed live under every answer inside Claude" width="60%">

Groundlens MCP inside Claude
</div>


## Table of contents

- [🧭 What is Groundlens](#-what-is-groundlens)
- [🚀 The basics](#-the-basics)
- [:jigsaw: Integrate it](#-integrate-it)
- [:notebook_with_decorative_cover: Tutorials](#-tutorials)
- [📍 Compliance mapping](#-compliance-mapping)
- [📄 Research](#-research)
- [🤝 Contributing](#-contributing)

---

## 🧭 What is Groundlens

An LLM will answer confidently whether or not it used the document you gave it. Sometimes it draws on the source; sometimes it answers from memory, or drifts to the topic of the question. You cannot tell which just by reading the answer, and re-reading every answer by hand, or paying a second LLM to judge each one, does not scale.

Groundlens measures the *geometry* of an answer, where it sits relative to its source and to the question, and turns that into a plain reading: **did this answer come from the source, or not?** It runs in milliseconds, gives the same result every time, and uses no second language model. Its job is to let the clearly grounded answers through and flag the ones worth a closer look, so the slow and expensive checks only run where they are needed.

> **Groundlens does not measure truth.** It measures grounding: whether an answer came from its source (SGI) or moves like a well grounded answer (DGI). A statement that is factually wrong but well grounded in the source can pass, and a true statement that ignores the source can be flagged. For truth you need a source of truth: a lookup, a knowledge base, a rule, or a person. Groundlens tells you which answers to send there.

Checking an LLM's output is a pipeline, cheapest step first. Groundlens is the front of it and decides what reaches the expensive back.

| # | Step | The question it answers | Included |
|---|---|---|---|
| 1 | **Geometry** (SGI / DGI) | Did the answer come from its source, or drift off it? | YES |
| 2 | **Consistency** | When there is no source to compare against, does the model agree with itself? | YES |
| 3 | **Rules** | Did the answer break a specific policy, invent a number, skip a required disclosure? | YES
| 4 | **LLM as judge** | The hard cases that need real reasoning over the evidence. | NO |
| 5 | **Human Review** | The last step of the pipeline. | NO |

Groundlens covers steps 1 to 3 and needs no second LLM. Steps 4 and 5 run only on what the earlier steps flag.
---

## 🚀 The basics

```bash
pip install groundlens
```

Four checks, each answering a different question. You rarely need all of them; pick the one that fits your case.

### SGI: did the answer come from its source?

This is the core. You give Groundlens a question, an answer, and (when you have it) the source the answer was supposed to use. It returns a reading.

- Use **SGI** when you have the retrieved source (a RAG pipeline: you know which document the model was given).


```python
from groundlens import compute_sgi, check

question = "How long do international transfers take, and is there a fee?"
context = (
    "International transfers sent before 3:00 PM on a business day are processed the same day and "
    "typically arrive within 1 to 3 business days, depending on the destination country and the "
    "receiving bank. A flat fee of 15 EUR applies per international transfer, except for transfers "
    "within the SEPA area, which are exempt."
)
response = (
    "International transfers sent before 3:00 PM on a business day usually arrive within 1 to 3 "
    "business days. There is a flat 15 EUR fee per transfer, and SEPA transfers are exempt."
)

sgi = compute_sgi(question=question, context=context, response=response)
print(check(sgi).render())
# CHECK: Supported by the document (Semantic Grounding Index - SGI=...)
# The answer draws on the source and does not add claims beyond it.
```

Read the **level**, not the decimal. `check(sgi).level` is `"ok"`, `"review"`, or `"risk"`, and that is what you act on. The raw SGI number depends on which embedding model you use, so it is a relative signal, not an absolute grade.

| Reading | SGI (default encoder) |
|---|---|
| :green_circle: came from the source | 1.20 or higher |
| :orange_circle: partly | 0.95 to 1.20 |
| :stop_sign: not from the source | below 0.95 |

### DGI: check an answer when there is no source

When there is no retrieved document (one-shot prompting, tool use, an agent talking to itself), SGI has nothing to compare against. DGI works from the question and the answer alone: it measures the *direction* the answer takes and compares it to how well-grounded answers usually move.


```python
from groundlens import compute_dgi, check

question = "What is compound interest, in simple terms?"
response = (
    "Compound interest is interest calculated on the original amount and on the interest already "
    "added, so a balance grows faster over time than it would with simple interest."
)

# One global reference direction:
reading = check(compute_dgi(question=question, response=response))

# Local variant (Gamma_k): a query-specific reference built from the k calibration
# questions nearest to yours. Sharper when your reference set spans several domains.
reading_local = check(compute_dgi(question=question, response=response, k=10))

print(reading_local.level, reading_local.label)   # act on the level, not the raw number
```

DGI is a directional triage signal, not a truth test, and it leans on the embedding model and the domain far more than SGI does. Its cut-points are not universal: they depend on your encoder and the style of your data, so read DGI as a relative ranking and set the operating point by calibrating on your own grounded set (see [Calibration](#-calibration)). It will not catch a confident wrong fact phrased like a right one; that is what the [consistency checks](#consistency-checks-does-the-model-agree-with-itself) and rules are for.

The local variant `k=...` shown above builds a query-specific reference from the calibration questions nearest to yours, which sharpens DGI when your reference set spans several domains.

### Consistency checks: does the model agree with itself?

Geometry has one blind spot: a confident answer that is wrong on a single fact but phrased exactly like a correct one (right topic, right wording, one wrong number). It sits right next to a grounded answer, so no geometric score separates them.

When there is no source to check against and DGI suggests that the answer could be wrong, you can ask the model again and see if it stays consistent. A model that knows the answer repeats it; a model that is guessing wanders. Groundlens provides two ways to measure that, and they differ in *what* you vary between samples:

- **Resample** — ask the *same* question several times with sampling on. Variation comes from the model's own randomness. Simple, but needs several samples.
- **Reword** — rephrase the *question* a few ways and answer each once. Variation comes from the input. It surfaces the signal with fewer calls, because one or two rewordings already expose a guess.

This check needs to generate text from a model, which pulls in heavy dependencies (`transformers`, `torch`). Those are **not** part of the core: `pip install groundlens` and `import groundlens` stay lightweight (just NumPy and the embedding model), and never load torch. You opt into the weight only when you need this stage, with the `verify` extra:

```bash
pip install "groundlens[verify]"
```

```python
from groundlens.verify import two_stage

result = two_stage(
    question="What is the standard maximum annual Roth IRA contribution for someone under 50 in 2024?",
    answer="The maximum is 8,000 USD.",               # confident, and wrong (it is 7,000)
    model="Qwen/Qwen2.5-7B-Instruct",                 # any HF model, or generator=... for an API
)
print(result.escalated)   # True: geometry couldn't settle it, so the model was resampled
print(result.final.render())   # the CHECK to act on, in the same plain language
```

The cut-points here are provisional; calibrate them on your own data with `fit_thresholds`. [Tutorial 3](https://github.com/groundlens-dev/groundlens/blob/main/examples/tutorials/03-consistency-checks.md) walks through both methods end to end.

**Use a hosted API instead of a local model.** The consistency checks accept any generator that exposes `generate` / `generate_many`. Groundlens ships ready-made adapters for Claude, GPT, Gemini, and any OpenAI-compatible endpoint, so you do not need a local GPU:

```python
from groundlens.verify import SampleConsistency, AnthropicGenerator, OpenAIGenerator, GeminiGenerator

q = "What is the standard maximum annual Roth IRA contribution for someone under 50 in 2024?"
a = "The maximum is 8,000 USD."   # confident, and wrong (it is 7,000)

# Claude, scored with the embedding scorer (reuses the SGI/DGI encoder, no torch)
checker = SampleConsistency(generator=AnthropicGenerator(model="claude-3-5-haiku-latest"), scorer="embedding")
print(checker.verify(question=q, answer=a).check.render())

# Swap the generator for GPT (or any OpenAI-compatible endpoint via base_url) or Gemini:
OpenAIGenerator(model="gpt-4o-mini")     # base_url=... for DeepSeek, vLLM, a local gateway
GeminiGenerator(model="gemini-1.5-flash")
```

Install the matching extra: `pip install "groundlens[anthropic]"`, `[openai]`, or `[google]`. The API key is read from the provider's usual environment variable, or pass `api_key=...`. The `embedding` scorer keeps this torch-free; the NLI scorer (`scorer="nli"`, more accurate) needs `pip install "groundlens[verify]"`.

> **Privacy.** With a hosted API, your prompts and answers go to that provider, using your key, under their terms. Groundlens holds no key and has no server in the path: it never sees or stores your data, and it cannot, there is nothing of ours in between. For a no-egress option, use the local model. Full detail, and how to verify it yourself, in [DATA_HANDLING.md](https://github.com/groundlens-dev/groundlens/blob/main/DATA_HANDLING.md).

### Rules: did the answer break a policy?

A **rule** is a small, named check that reads the answer and returns pass or fail with the evidence, and carries a citation to why it exists (a paper, a standard, a regulation or an internal rule). It catches the specific, mechanical failures geometry does not: an invented figure, a missing disclosure, a claim outside the agent's remit.

For example, the `no_invented_numbers` rule flags any number in the answer that does not appear in the source. You do not write it yourself; you pick a **rule set**, a bundle of rules for a kind of agent, and run it:

```python
from groundlens.agents import customer_support_rules

audit = customer_support_rules().evaluate(
        question=question,
        response=response,
        context=context,
)
print(audit.flagged)             # True: the answer said 500 EUR, the source says 1,000
print(audit.audit_explanation)   # per-rule trail: which rule fired, on what evidence, citing what
```

`customer_support_rules` is one of several bundles (`routing_rules`, `decision_rationale_rules`, `specialized_agent_rules`). You can also write your own rules from two small primitives, `RuleSet` and `ChecklistRule`. Full catalog and the build-your-own recipe: [rule sets guide](https://docs.groundlens.dev/guides/custom-rule-sets/).


After each generation, score the answer and write the result to a log.

```python
from groundlens import compute_sgi, check
from groundlens.agents import customer_support_rules
from groundlens.audit import open_log

rules = customer_support_rules()

with open_log("triage.db") as log:
    for question, context, response in your_pipeline_outputs:
        sgi   = compute_sgi(question=question, context=context, response=response)
        audit = rules.evaluate(question=question, response=response, context=context)
        flagged = check(sgi).level != "ok" or audit.flagged
        log.record(
            identifier=question,
            method="sgi+rules",
            score=sgi.normalized,
            flagged=flagged,
            inputs={"response": response, "context": context},
            metadata={"audit": audit.audit_explanation},
        )
        send_to_review(response) if flagged else send_to_user(response)
```

The log is hash-chained, so any decision can be replayed and verified byte-for-byte later. Framework-specific snippets (LangChain, LangGraph, CrewAI, Semantic Kernel, AutoGen) are in the [integrations docs](https://docs.groundlens.dev/integrations/).


---

## :jigsaw:	 Integrate it

To wire groundlens into an agent pipeline it ships adapters that score every model response for you and collect the readings.

```bash
pip install "groundlens[langchain]"     # Available integrations: [langgraph], [crewai], [semantic-kernel], [autogen]
```

**LangChain.** Attach `GroundlensCallback` to any chain. It scores every LLM response (SGI when you pass the retrieved context, DGI otherwise) and accumulates the readings in `.scores`:

```python
from groundlens import check
from groundlens.integrations.langchain import GroundlensCallback

cb = GroundlensCallback(context_key="context")   # reads the source from run metadata

rag_chain.invoke(
    question,
    config={"callbacks": [cb], "metadata": {"context": retrieved_context}},
)

# after the run, inspect what Groundlens saw on each response
for run_id, score in cb.scores.items():
    print(check(score).render())
```

Full runnable script: [`examples/langchain_evaluator.py`](https://github.com/groundlens-dev/groundlens/blob/main/examples/langchain_evaluator.py).

You can find examples of how to integrate groundlens with other frameworks here:

| Framework | Adapter | Example |
|---|---|---|
| LangGraph | `GroundlensLangGraphCallback` (per-node scoring) | [docs](https://docs.groundlens.dev/integrations/) |
| CrewAI | tool wrapper | [`examples/crewai_tool.py`](https://github.com/groundlens-dev/groundlens/blob/main/examples/crewai_tool.py) |
| Semantic Kernel | output filter | [`examples/semantic_kernel_filter.py`](https://github.com/groundlens-dev/groundlens/blob/main/examples/semantic_kernel_filter.py) |
| AutoGen | `groundlens[autogen]` | [docs](https://docs.groundlens.dev/integrations/) |

No adapter for your stack? Call `compute_sgi` / `compute_dgi` / `ruleset.evaluate` after each generation yourself, the pattern shown under [Rules](#rules-did-the-answer-follow-a-policy).

### MCP Server

Prefer to see the check inside your editor or chat? The Groundlens MCP server runs the same first-stage check inside Claude Desktop, Cursor, and VS Code, printing a CHECK under each answer with no model in the scoring path.

| Client | Install |
|---|---|
| Cursor | [![Install in Cursor](https://img.shields.io/badge/Cursor-Add_MCP-000000?style=flat-square&logo=cursor&logoColor=white)](https://cursor.com/install-mcp?name=groundlens&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJncm91bmRsZW5zLW1jcCJdfQ%3D%3D) |
| VS Code | [![Install in VS Code](https://img.shields.io/badge/VS_Code-Add_MCP-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=groundlens&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22groundlens-mcp%22%5D%7D) |

Full setup: [groundlens-dev/groundlens-mcp](https://github.com/groundlens-dev/groundlens-mcp).

---

## :notebook_with_decorative_cover: Tutorials

Several tutorials are available at [`examples/tutorials/`](https://github.com/groundlens-dev/groundlens/tree/main/examples/tutorials).

- **Tutorial 1 — Catch an answer that invents a number** (below)
- **[Tutorial 2 — Check a chat answer that has no source](https://github.com/groundlens-dev/groundlens/blob/main/examples/tutorials/02-chat-no-source.md)** (DGI)
- **[Tutorial 3 — Catch the confident wrong fact geometry misses](https://github.com/groundlens-dev/groundlens/blob/main/examples/tutorials/03-consistency-checks.md)** (consistency checks)
- **[Tutorial 4 — Audit a regulated decision](https://github.com/groundlens-dev/groundlens/blob/main/examples/tutorials/04-audit-regulated-decision.md)** (rules + hash-chained log)

### Tutorial 1: Catch an answer that invents a number

**The problem.** A retail bank runs a support assistant over its FAQ. Most answers are fine, but now and then the model states a figure that is not in the source, a wrong transfer limit, an invented fee. Those must be caught before they reach a customer.

**The tools.** Two, because they catch different things. **SGI** tells you whether the answer engaged the source at all. A **rule** (`no_invented_numbers`) points at the exact figure that is wrong. You flag if either fires.

**Step 1 — install.**

```bash
pip install groundlens
```

**Step 2 — set up one grounded case and one that invents a number.**

```python
from groundlens import compute_sgi, check
from groundlens.agents import customer_support_rules

question = "What is the daily transfer limit?"
context  = "The daily transfer limit is 1,000 $ per transaction and 2,000 $ per day."

grounded = "The daily limit is 1,000 $ per transaction and 2,000 $ per day."
invented = "The daily limit is 500 $ per transaction, and 10,000 $ for premium clients."

rules = customer_support_rules()   #this is a ptr-frgin
```

**Step 3 — score both answers.**

```python
for label, answer in [("grounded", grounded), ("invented", invented)]:
    sgi   = compute_sgi(question=question, context=context, response=answer)
    audit = rules.evaluate(question=question, response=answer, context=context)
    flagged = check(sgi).level != "ok" or audit.flagged
    print(f"[{label}] level={check(sgi).level}  rule_flagged={audit.flagged}  -> FLAG={flagged}")
```

**Step 4 — read the result.** The grounded answer passes both checks. The invented one is flagged: the `no_invented_numbers` rule fires on `500` and `10,000`, neither of which is in the source. Print the trail to see exactly why:

```python
audit = rules.evaluate(question=question, response=invented, context=context)
print(audit.audit_explanation)
```

**How to read it.** SGI answers *did it come from the source*; the rule answers *which specific fact is wrong and on what authority*. Together they give you one flag per answer plus an audit line you can keep. Note that the raw SGI number shifts with your embedding model, so in production you act on the **level** and the **rule flags**, not the decimal, and you set the level thresholds by [calibrating on your own data](https://docs.groundlens.dev/guides/domain-calibration/).

**Next.** Route every flagged answer to a person, and log the rest. That is the loop in [Integrate it](#-integrate-it) above.

---

## 📍 Compliance mapping

Data handling, privacy, and how to verify Groundlens sends nothing out: [DATA_HANDLING.md](https://github.com/groundlens-dev/groundlens/blob/main/DATA_HANDLING.md).


Groundlens ships mappings from its components to specific regulatory clauses, and a hash-chained audit log that makes any decision reproducible byte-for-byte, which is what these frameworks ask for in practice:

[SR 26-2](https://github.com/groundlens-dev/groundlens/blob/main/docs/guides/sr-11-7.md) · [EU AI Act 2024/1689](https://github.com/groundlens-dev/groundlens/blob/main/docs/guides/eu-ai-act.md) · [NIST AI RMF 1.0](https://github.com/groundlens-dev/groundlens/blob/main/docs/guides/nist-ai-rmf.md) · [Banking deployment](https://github.com/groundlens-dev/groundlens/blob/main/docs/guides/banking-deployment.md)

## 📄 Research

The methods are documented in three preprints:

| Paper | Link |
|---|---|
| *Semantic Grounding Index: geometric bounds on context engagement in RAG systems* (2025) | [arXiv:2512.13771](https://arxiv.org/abs/2512.13771) |
| *A Geometric Taxonomy of Hallucinations in LLMs* (2026) | [arXiv:2602.13224](https://arxiv.org/abs/2602.13224) |
| *How Transformers Reject Wrong Answers* (2026) | [arXiv:2603.13259](https://arxiv.org/abs/2603.13259) |

## 🤝 Contributing

Contributions and feedback are welcome. See [CONTRIBUTING.md](https://github.com/groundlens-dev/groundlens/blob/main/CONTRIBUTING.md).

## ⚖️ License

[![License: Apache](https://img.shields.io/badge/license-Apache%202-green?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)

Apache-2.0. Groundlens is named for the idea that a hallucination is something not grounded in reality.
