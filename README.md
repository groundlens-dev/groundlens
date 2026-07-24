<div align="center">
<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/logo.png" alt="Groundlens" width="140">

# Groundlens

### Check whether an LLM's answer actually came from its source.<br>Fast, cheap, and the same result every time.

[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![Version](https://img.shields.io/badge/version-2026.7.14-orange?style=flat-square)](https://github.com/groundlens-dev/groundlens/releases)
[![License: Apache](https://img.shields.io/badge/license-Apache%202-green?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/groundlens-dev/groundlens?style=flat-square&label=OpenSSF%20Scorecard)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)

<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/groundlens_claude_mcp.gif" alt="A grounding CHECK printed live under every answer inside Claude" width="62%">

<sub>A deterministic CHECK printed under every answer, live inside Claude.</sub>

</div>

---

## The verification pipeline

You have to verify every LLM call. You can't afford to verify them all the expensive way.

Verification is a pipeline of **five stages, ordered cheapest to most expensive**. Each stage is a filter: it settles what it can and passes only the doubtful cases forward. **Groundlens is stages 1–3** — so the slow, costly stages 4–5 only ever see the few answers that were actually flagged.

<div align="center">
<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/pipeline.png" alt="Five-stage verification pipeline: stages 1-3 (Geometry, Consistency, Rules) are Groundlens; stages 4-5 (LLM as judge, Human review) you add. Each stage filters what reaches the next." width="100%">
</div>

| # | Stage | The question it answers | Cost | In Groundlens |
|---|---|---|---|---|
| 1 | **Geometry** — SGI / DGI | Did the answer come from its source, or drift off it? | no model · deterministic | ✅ |
| 2 | **Consistency** | No source? Does the model agree with itself when asked again? | small open model · cheap | ✅ |
| 3 | **Rules** | Did it break a policy, invent a number, skip a disclosure? | deterministic | ✅ |
| 4 | **LLM as judge** | The hard cases that need real reasoning over the evidence. | frontier API · costs tokens | — you add |
| 5 | **Human review** | A person makes the final call. | costs a person | — you add |

> **This is the whole reason Groundlens exists.** Use it as triage at the front of the pipeline: clear the obvious cases in milliseconds and escalate only what's flagged to a judge model or a human. Same coverage on every call — a fraction of the time and cost.

> **SGI and DGI measure grounding, not truth.** They tell you whether an answer is *grounded* in its source — not whether it is *true*. A **hallucination** (an answer not grounded in the source it was given) phrased faithfully can still score as grounded. That gap is exactly why **Stage 2, Consistency, probes truth** by resampling the model. Read an SGI/DGI score as *"did this come from the source?"*, and lean on Stage 2 for *"does the model actually know this?"*

---

## What Groundlens does

An LLM answers with the same confidence whether or not it used the document you gave it. You can't tell which just by reading the reply, and re-reading every answer by hand — or paying a second LLM to judge each one — doesn't scale.

Groundlens measures the **geometry** of an answer: where it sits relative to its source and its question. From that it reads one thing — *did this come from the source, or not?* — in milliseconds, with the same result every time, letting the clearly-grounded answers through so the slow checks only run where they're needed.

---

## Quick setup

```bash
pip install groundlens
```

`pip install groundlens` stays light — just NumPy and an embedding model, **no torch**. The four checks below each answer a different question; you rarely need all of them, so pick the one that fits your case.

---

## The four checks

### 1 · SGI — did the answer come from its source?

The core check. Use it when you have the retrieved source (a RAG pipeline: you know which document the model was given).

```python
from groundlens import compute_sgi, check

question = "How long do international transfers take, and is there a fee?"
context  = (
    "International transfers sent before 3:00 PM on a business day are processed the same "
    "day and typically arrive within 1 to 3 business days. A flat fee of 15 EUR applies per "
    "international transfer, except within the SEPA area, which is exempt."
)
response = (
    "International transfers sent before 3:00 PM usually arrive within 1 to 3 business days. "
    "There is a flat 15 EUR fee per transfer, and SEPA transfers are exempt."
)

print(check(compute_sgi(question=question, context=context, response=response)).render())
# CHECK: Supported by the document (SGI)
# The answer draws on the source and does not add claims beyond it.
```

**Read the level, not the decimal.** `check(sgi).level` is `"ok"`, `"review"`, or `"risk"` — that's what you branch on. The raw number depends on your embedding model, so it's a relative signal.

| Reading | SGI (default encoder) |
|---|---|
| 🟢 came from the source | 1.20 or higher |
| 🟠 partly | 0.95 – 1.20 |
| 🔴 not from the source | below 0.95 |

Four real answers, scored with the default encoder:

| The answer | SGI | Reading |
|---|---|---|
| Faithful, straight from the source | **4.39** | 🟢 Supported |
| Faithful paraphrase of the source | **1.25** | 🟢 Supported |
| Restates the question without answering | **0.78** | 🔴 Not supported |
| Same wording, one wrong figure *(the blind spot)* | **1.11** | 🟠 Partly |

### 2 · DGI — check an answer when there is no source

No retrieved document (one-shot prompting, tool use, an agent talking to itself)? DGI works from the question and answer alone, measuring the *direction* the answer takes against how grounded answers usually move.

```python
from groundlens import compute_dgi, check

question = "What is compound interest, in simple terms?"
response = (
    "Compound interest is interest on the original amount and on the interest already added, "
    "so a balance grows faster over time than with simple interest."
)

reading = check(compute_dgi(question=question, response=response))
# local variant: a query-specific reference from the k nearest calibration questions
reading = check(compute_dgi(question=question, response=response, k=10))
print(reading.level, reading.label)   # act on the level, not the raw number
```

Measured on the shipped 212-pair reference set (real questions, each with a grounded and a fabricated answer). At the calibrated cut of **0.525**, grounded answers land above it and fabricated ones below:

| Domain | DGI — grounded | DGI — fabricated |
|---|---|---|
| Finance | **0.66** 🟢 | 0.51 🔴 |
| Medical | **0.65** 🟢 | 0.52 🔴 |
| Science | **0.55** 🟢 | 0.47 🔴 |
| Law | **0.57** 🟢 | 0.43 🔴 |

Across the full set: **AUROC 0.78** with the global direction, **0.81** with the local variant. DGI is directional triage, not a truth test — it leans on the encoder and domain more than SGI, so calibrate the cut-point on your own grounded set. It won't catch a confident wrong fact phrased like a right one; that's what Stage 2 is for.

### 3 · Consistency — does the model agree with itself?

Geometry's blind spot: an answer wrong on a single fact but phrased exactly like a correct one. When there's no source and DGI is uncertain, ask the model again — one that knows repeats itself, one that's guessing wanders.

```bash
pip install "groundlens[verify]"    # opt-in; pulls in transformers/torch only for this stage
```

```python
from groundlens.verify import two_stage

result = two_stage(
    question="What is the max annual Roth IRA contribution for someone under 50 in 2024?",
    answer="The maximum is 8,000 USD.",          # confident, and wrong (it is 7,000)
    model="Qwen/Qwen2.5-7B-Instruct",            # any HF model, or an API generator
)
print(result.escalated)        # True: geometry couldn't settle it, so the model was resampled
print(result.final.render())   # the CHECK to act on
```

Two ways to measure it: **Resample** (same question, sampling on) and **Reword** (rephrase the question a few ways). No local GPU? Ready-made adapters for Claude, GPT, Gemini, and any OpenAI-compatible endpoint — the `embedding` scorer keeps it torch-free.

```python
from groundlens.verify import SampleConsistency, AnthropicGenerator

checker = SampleConsistency(
    generator=AnthropicGenerator(model="claude-3-5-haiku-latest"), scorer="embedding",
)
print(checker.verify(question=q, answer=a).check.render())
```

> **Privacy.** With a hosted API, your prompts go to that provider under your key. Groundlens holds no key and has no server in the path — it never sees or stores your data. For a no-egress option, use a local model. Detail in [DATA_HANDLING.md](https://github.com/groundlens-dev/groundlens/blob/main/DATA_HANDLING.md).

### 4 · Rules — did the answer break a policy?

A small, named check that returns pass/fail with evidence and a citation to why it exists. Catches the mechanical failures geometry doesn't: an invented figure, a missing disclosure, a claim outside the agent's remit.

```python
from groundlens.agents import customer_support_rules

audit = customer_support_rules().evaluate(question=question, response=response, context=context)
print(audit.flagged)            # True: said 500 EUR, source says 1,000
print(audit.audit_explanation)  # per-rule trail, each citing why it fired
```

Bundled sets: `customer_support_rules`, `routing_rules`, `decision_rationale_rules`, `specialized_agent_rules`. Write your own from `RuleSet` + `ChecklistRule`.

---

## Score every answer, keep the trail

```python
from groundlens import compute_sgi, check
from groundlens.agents import customer_support_rules
from groundlens.audit import open_log

rules = customer_support_rules()

with open_log("triage.db") as log:
    for question, context, response in your_pipeline_outputs:
        sgi     = compute_sgi(question=question, context=context, response=response)
        audit   = rules.evaluate(question=question, response=response, context=context)
        flagged = check(sgi).level != "ok" or audit.flagged
        log.record(identifier=question, method="sgi+rules", score=sgi.normalized,
                   flagged=flagged, metadata={"audit": audit.audit_explanation})
        (send_to_review if flagged else send_to_user)(response)
```

The log is **hash-chained** — any decision can be replayed and verified byte-for-byte, years later.

---

## Integrate it

```bash
pip install "groundlens[langchain]"   # also: langgraph · crewai · semantic-kernel · autogen
```

```python
from groundlens import check
from groundlens.integrations.langchain import GroundlensCallback

cb = GroundlensCallback(context_key="context")   # SGI when context is present, DGI otherwise
rag_chain.invoke(question, config={"callbacks": [cb], "metadata": {"context": retrieved_context}})
for run_id, score in cb.scores.items():
    print(check(score).render())
```

No adapter for your stack? Call `compute_sgi` / `compute_dgi` / `ruleset.evaluate` after each generation yourself — same pattern.

**In your editor** — the [MCP server](https://github.com/groundlens-dev/groundlens-mcp) prints a CHECK under every answer inside Claude, Cursor, and VS Code, with no model in the scoring path.

[![Add to Cursor](https://img.shields.io/badge/Cursor-Add_MCP-000000?style=flat-square&logo=cursor&logoColor=white)](https://cursor.com/install-mcp?name=groundlens&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJncm91bmRsZW5zLW1jcCJdfQ%3D%3D)
[![Add to VS Code](https://img.shields.io/badge/VS_Code-Add_MCP-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=groundlens&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22groundlens-mcp%22%5D%7D)

---

## Learn more

- 📚 **Docs** — [docs.groundlens.dev](https://docs.groundlens.dev)
- 🧪 **Tutorials** — [`examples/tutorials/`](https://github.com/groundlens-dev/groundlens/tree/main/examples/tutorials)
- 🎮 **Live demo** — [Hugging Face Space](https://huggingface.co/spaces/groundlens/demo)
- 📍 **Compliance** — [SR 26-2](https://github.com/groundlens-dev/groundlens/blob/main/docs/guides/sr-11-7.md) · [EU AI Act](https://github.com/groundlens-dev/groundlens/blob/main/docs/guides/eu-ai-act.md) · [NIST AI RMF](https://github.com/groundlens-dev/groundlens/blob/main/docs/guides/nist-ai-rmf.md)
- 📄 **Research** — [SGI (arXiv:2512.13771)](https://arxiv.org/abs/2512.13771) · [Hallucination taxonomy (arXiv:2602.13224)](https://arxiv.org/abs/2602.13224) · [How transformers reject wrong answers (arXiv:2603.13259)](https://arxiv.org/abs/2603.13259)

---

## Contributing

Contributions and feedback are welcome — see [CONTRIBUTING.md](https://github.com/groundlens-dev/groundlens/blob/main/CONTRIBUTING.md).

## License

Apache-2.0. Groundlens is named for the idea that a hallucination is something not grounded in reality.

