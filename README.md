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


## The verification pipeline

You have to verify every LLM call. You can't afford to verify them all the expensive way.

Verification is a pipeline of **five stages, ordered cheapest to most expensive**. Each stage is a filter: it settles what it can and passes only the doubtful cases forward. **Groundlens is stages 1–3** — so the slow, costly stages 4–5 only ever see the few answers that were actually flagged.

<div align="center">
<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/pipeline.png" alt="Five-stage verification pipeline: stages 1-3 (Geometry, Consistency, Rules) are Groundlens; stages 4-5 (LLM as judge, Human review) you add. Each stage filters what reaches the next." width="100%">
</div>

| Stage | Approach | The question it answers | Cost | Groundlens |
|---|---|---|---|---|
| 1 | **Geometry**  | Did the answer come from its source, or drift off it? | no model · deterministic | Included |
| 2 | **Consistency** | No source? Does the model agree with itself when asked again? | small open model · cheap | Included |
| 3 | **Rules** | Did it break a policy, invent a number, skip a disclosure? | deterministic | Included |
| 4 | **LLM as judge** | The hard cases that need real reasoning over the evidence. | frontier API · costs tokens | Not included |
| 5 | **Human review** | A person makes the final call. | costs a person | Not included |

</div>

> **This is the whole reason Groundlens exists.** Use it as triage at the front of the pipeline: clear the obvious cases in milliseconds and escalate only what's flagged to a judge model or a human reviewer. Same coverage on every call — a fraction of the time and cost.

> **SGI and DGI measure grounding, not truth.** They tell you whether an answer is *grounded* in its source — not whether it is *true*. A **hallucination** (an answer not grounded in the source it was given) phrased faithfully can still score as grounded. That gap is exactly why **Stage 2, Consistency, probes truth** by resampling the model. Read an SGI/DGI score as *"did this come from the source?"*, and lean on Stage 2 for *"does the model actually know this?"*


## What Groundlens does

An LLM answers with the same confidence whether or not it used the document you gave it. You can't tell which just by reading the reply, and re-reading every answer by hand — or paying a second LLM to judge each one — doesn't scale.

Groundlens measures:
- the **geometry** of an answer: where it sits relative to its source and its question. From that it reads one thing — *did this come from the source, or not?* — in milliseconds, with the same result every time, letting the clearly-grounded answers through so the slow checks only run where they're needed.
- the **consistency** of an answer across different calls to check if the model agree with itself.


## Quick setup

```bash
pip install groundlens
```

`pip install groundlens` stays light — just NumPy and an embedding model, **no torch**. The four checks below each answer a different question; you rarely need all of them, so pick the one that fits your case.


## Stage 1

### Semantic Grounding Index -SGI: did the answer come from its source?

The core check. Use it when you have the retrieved source (a RAG pipeline: you know which document the model was given).

```python
from groundlens import compute_sgi, check

question = (
    "A user of our cloud backup service wants to understand the data retention rules for the "
    "Business plan: how long deleted files can still be recovered, what happens to backups when a "
    "subscription is cancelled, and whether any of this differs for files under a legal hold."
)

context = (
    "On the Business plan, deleted files are moved to a recovery area and can be restored for 90 "
    "days from the date of deletion; after 90 days they are permanently purged and cannot be "
    "recovered. Version history is kept for up to 180 days per file. When a subscription is "
    "cancelled, the account enters a 30-day grace period during which all backups remain intact and "
    "fully restorable; if the plan is not renewed within those 30 days, every backup associated with "
    "the account is permanently deleted. Files placed under a legal hold are exempt from both the "
    "90-day purge and the cancellation deletion: they are preserved unchanged until the hold is "
    "explicitly lifted by an administrator, regardless of deletion date or subscription status."
)

# 1) Answer that stays on the source
answer_grounded = (
    "On the Business plan you can restore a deleted file for 90 days after it was deleted; once those "
    "90 days pass it is purged for good. Each file also keeps up to 180 days of version history. If you "
    "cancel the subscription there is a 30-day grace period where all backups stay restorable, but if "
    "you do not renew within that window everything is permanently deleted. Files under a legal hold "
    "are the exception: they are preserved until an administrator lifts the hold, no matter when they "
    "were deleted or whether the plan is still active."
)
sgi_grounded = compute_sgi(question=question, context=context, response=answer_grounded)
print("SGI grounded   :", round(sgi_grounded.value, 2), "|", check(sgi_grounded).label)

# 2) Answer that leaves the source
answer_ungrounded = (
    "Deleted files on the Business plan are kept forever and can always be restored at any time, so "
    "there is no purge window to worry about. Cancelling the subscription has no effect on your "
    "backups, and they stay available indefinitely even without an active plan. Legal holds are not "
    "supported, so every file is treated exactly the same way."
)
sgi_ungrounded = compute_sgi(question=question, context=context, response=answer_ungrounded)
print("SGI ungrounded :", round(sgi_ungrounded.value, 2), "|", check(sgi_ungrounded).label)
```

```json
Results:
grounded    SGI=  2.29  -> ok      Supported by the document
off-source  SGI=  1.01  -> review  Partly supported
```

**Interpretation**: SGI sorts every answer into one of three segments. In two of them the geometry is clear: at or above 1.20 the answer is grounded in the source, below 0.95 it is not. Between them, from 0.95 to 1.20, sits the third segment, where the geometric signal is uncertain and cannot settle the case on its own. The two clear segments you can act on right away, pass or flag. The uncertain middle is what you send to the second stage.

| SGI below 0.95 | SGI between 0.95 and 1.2 | SGI higher than 1.2 | 
|---|---|---|
| 🟢 came from the source | 🟠 partly grounded | 🔴 not from the source |


### Directional Grounding Index -DGI: check if the answer is aligned with the question when there is no source

No retrieved document (one-shot prompting, tool use, an agent talking to itself)? DGI works from the question and answer alone, measuring the *direction* the answer takes against how grounded answers usually move.

```python
from groundlens import compute_dgi, check

# ---- Example 1: finance — a grounded answer (expected around 0.6) ----
question_1 = (
    "What is the difference between a traditional IRA and a Roth IRA?"
)
answer_grounded = (
    "The main tax difference is when you pay taxes. With a traditional IRA, contributions are "
    "typically tax-deductible now, but you pay income taxes on withdrawals in retirement. With a "
    "Roth IRA, contributions are made with after-tax dollars (no upfront deduction), but qualified "
    "withdrawals in retirement are completely tax-free."
)
dgi_grounded = compute_dgi(question=question_1, response=answer_grounded)
print("DGI grounded   :", round(dgi_grounded.value, 2), "|", check(dgi_grounded).label)

# ---- Example 2: medical — a fabricated answer (expected below the cut) ----
question_2 = "What is the primary function of red blood cells?"
answer_fabricated = (
    "Red blood cells have as their primary function to provide the characteristic red coloration to "
    "blood, which serves as a visual indicator of circulatory system health during medical "
    "examinations. The intensity of the red color correlates directly with overall cardiovascular "
    "fitness and oxygen saturation levels. Pale blood coloration typically indicates anemia or "
    "reduced physical conditioning."
)
dgi_fabricated = compute_dgi(question=question_2, response=answer_fabricated)
print("DGI fabricated :", round(dgi_fabricated.value, 2), "|", check(dgi_fabricated).label)
```

```json
Results:
DGI grounded   : 0.54 | Looks aligned with the question
DGI fabricated : 0.37 | Not aligned with the quesion
```

**Interpretation**:DGI uses a single cut, not three segments. At or above the cut the answer moves like a grounded one; below it, like a fabrication. The cut sits near 0.52 with the global reference direction and 0.54 with the local variant. That value is not universal: it depends on your encoder and the kind of text you check, so read DGI as a relative ranking rather than an absolute grade. Calibrate the cut on your own grounded answers for a specific domain (see `fit_thresholds`) and the separation gets sharper.

## Stage 2

### Consistency — does the model agree with itself?

Geometry's blind spot: an answer wrong on a single fact but phrased exactly like a correct one. When there's no source and DGI is uncertain, ask the model again — one that knows repeats itself, one that's guessing wanders.

- Example 1:

```python
import torch
from groundlens.verify import SelfCheckNLI, two_stage

MODEL = "Qwen/Qwen2.5-3B-Instruct"   # any HF instruct model; bump to 7B on an L4/A100
detector = SelfCheckNLI(model=MODEL, n_samples=5)   # loads once; reused below

question = "How long do international transfers take, and is there a fee?"
context = (
    "International transfers sent before 3:00 PM on a business day arrive within 1 to 3 business "
    "days. A flat 15 EUR fee applies, except within the SEPA area, which is exempt."
)
answer = (
    "Transfers sent before 3:00 PM on a business day usually arrive within 1 to 3 business days. "
    "There is a flat 15 EUR fee, and SEPA transfers are exempt."
)

r1 = two_stage(question=question, answer=answer, context=context, detector=detector)

print("escalated:", r1.escalated)            # False: geometry settled it, no model call
print("stage 1  :", r1.stage1.label)
print("final    :", r1.final.render())
```

```json
escalated: False
stage 1  : Supported by the document
final    : CHECK: Supported by the document (Semantic Grounding Index - SGI=2.62)
The answer draws on the source and adds detail beyond the question.
Grounding, not facts: a plausible wrong fact in the right frame would pass this check. Verify facts in a second stage.
```

The answer really came from the source. Stage one scored SGI 2.62, well above the 1.20 line, marked it "Supported," and escalated was False. The key part is what it did not do: it never loaded or called the model. The easy, grounded case was cleared for free. That is the whole point of a cheap first stage.


- Example 2: 

```
import torch
from groundlens.verify import SelfCheckNLI, two_stage
question = "What is the primary function of red blood cells?"
answer = (
    "Red blood cells provide the characteristic red coloration to blood, which serves as a visual "
    "indicator of circulatory health during medical examinations. The intensity of the red color "
    "correlates directly with cardiovascular fitness."
)

r2 = two_stage(question=question, answer=answer, detector=detector)   # no context -> DGI first

print("escalated:", r2.escalated)            # True: geometry could not settle it
print("stage 1  :", r2.stage1.label)
if r2.stage2 is not None:
    print("consistency:", round(r2.stage2.consistency, 2))
    print("samples    :", list(r2.stage2.samples))
print("final    :", r2.final.render())
```

```json
escalated: True
stage 1  : Not grounded
consistency: 0.36
samples    : ['To carry oxygen throughout the body.', 'To transport oxygen throughout the body.', 'To carry oxygen throughout the body.', 'Transport oxygen throughout the body.', 'Transport oxygen throughout the body.']
final    : CHECK: Inconsistent answer (Sample Consistency - SC=0.36)
The model gives different answers across samples, a common sign of a made-up answer. Check it before trusting it.
Provisional cut-points; calibrate with fit_thresholds on your data.
The model does not answer consistently here. Send it to a human reviewer.
```

The answer was made up (red blood cells "give blood its color"), with no source to check against. Stage one used DGI, said "Not grounded," and escalated. Stage two then asked the model itself five times. All five samples said the correct thing ("carry/transport oxygen"), which disagrees with the answer under test. Consistency fell to 0.36, below the cut, so it was flagged "Inconsistent" and sent to a human. The fabrication got caught, and by a different mechanism than the geometry: not by shape, but because the model itself won't back the claim.


## Stage 3 · Rules — did the answer break a policy?

A small, named check that returns pass/fail with evidence and a citation to why it exists. Catches the mechanical failures geometry doesn't: an invented figure, a missing disclosure, a claim outside the agent's remit.

```python
from groundlens.agents import customer_support_rules

audit = customer_support_rules().evaluate(question=question, response=response, context=context)
print(audit.flagged)            # True: said 500 EUR, source says 1,000
print(audit.audit_explanation)  # per-rule trail, each citing why it fired
```

Bundled sets: `customer_support_rules`, `routing_rules`, `decision_rationale_rules`, `specialized_agent_rules`. Write your own from `RuleSet` + `ChecklistRule`.


## Privacy

With a hosted API, your prompts go to that provider under your key. Groundlens holds no key and has no server in the path — it never sees or stores your data. For a no-egress option, use a local model. Detail in [DATA_HANDLING.md](https://github.com/groundlens-dev/groundlens/blob/main/DATA_HANDLING.md).

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

