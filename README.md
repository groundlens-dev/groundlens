<div align="center">

# Groundlens: deterministic first-stage verification layer for agentic RAG and regulated systems


[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13%20|%203.14-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![PyPI](https://img.shields.io/pypi/v/groundlens?style=flat-square&label=version&color=orange)](https://pypi.org/project/groundlens/)
[![License: Apache](https://img.shields.io/badge/license-Apache%202-green?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/groundlens-dev/groundlens?style=flat-square&label=OpenSSF%20Scorecard)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)

[Live demo](https://huggingface.co/spaces/groundlens/demo) · [Docs](https://docs.groundlens.dev) · [Docs](https://docs.groundlens.dev) · [MCP server](https://github.com/groundlens-dev/groundlens-mcp) · [Benchmarks](BENCHMARKS.md)

</div>

## What is Groundlens

Groundlens is not another hallucination detector that tells you if the answer is true. Groundlens is a local verification layer that sits in front of expensive checks. It answers three practical questions without calling a second LLM:

- Did this answer engage the source it was given   , or did it stay aligned with the question?
- May this answer be written into agent or RAG state, or would it contaminate later turns?
- Does the answer break any of the explicit policy or completeness rules defined for this domain?

Geometry ranks source engagement. Rules catch policy and completeness violations. A switch decides what may enter agent state. The deterministic stages run locally, cost nothing per request, and return the same result every time. The hard cases are left for an LLM judge or a human. Geometry (SGI/DGI) provides a fast ranking signal. Rules provide hard, auditable constraints. The Switch turns the ranking into a state-write decision. An optional consistency stage can resample a small local model on the remaining cases. The expensive stages — an LLM judge and a human — only ever see what the earlier stages could not settle.

| When to use Groundlens | 
| :-- |
| Use Groundlens when you need a zero-cost, reproducible filter before a caseworker, a release gate, or a slower judge. It is strongest when you can express domain constraints as rules and when you care that the same input produces the same verdict tomorrow. It does not replace a judge on questions that require reading, and it does not cover the input surface (injection, harmful content)|



## The verification pipeline

<div align="center">
<img src="docs/assets/pipeline.png" alt="Six stages, cheapest first. Groundlens is stages 1–4: Geometry, Switch, Consistency, Rules. A switch decides what goes forward. Stages 5–6 (LLM judge and human review) are supplied by you." width="100%">
</div>

Groundlens is stages 1–4. They settle what they can and pass only the doubtful cases forward.

| Stage | What it answers | Model calls | Notes |
|-------|-----------------|-------------|-------|
| 1. Geometry (SGI/DGI) | Did the answer engage its source, or drift off it? | 0 | Ranks every answer |
| 2. Switch | May this answer enter agent state? | 0 | Deterministic accept / escalate |
| 3. Consistency | No source? Does the model agree with itself when asked again? | small local model, only if needed | Optional |
| 4. Rules | Did it break a policy, invent a number, skip a disclosure? | 0 | Named checks with evidence spans |

Not  included in groundlens:

| Stage | What it answers | Model calls | Notes |
|-------|-----------------|-------------|-------|
| 5. LLM as judge | Hard cases that need reasoning over the evidence | yes | You supply and pin |
| 6. Human review | Final call | — | Costliest check |

In practice a large fraction of answers can exit after the deterministic stages (1 to 4). The remainder is what justifies the slower checks.

## Tools included in Groundlens

| Tool | Stage |Use it to | Call |
|------| ----- |----------|------|
| **SGI** | 1 |Check an answer against the source it was given | `compute_sgi(question, context, response)` |
| **DGI** | 1 |Check an answer when there is no source. Calibrate first | `compute_dgi(question, response)` |
| **Check** | 1 |Turn any score into a plain-language reading | `check(score)` |
| **Switch** | 2 |Decide whether an answer may enter agent state | `GroundingSwitch().decide(score)` |
| **Consistency** | 3 | Ask the model again and measure agreement | `two_stage(question, answer, model=...)` |
| **Rules** | 4 |Check an answer against a written policy, with evidence | `decision_rationale_rules(domain=...).evaluate(...)` |
| **Calibrate** | 1 | Fit cuts and reference direction to your data | `fit_thresholds(examples)` |
| **Audit** | 1-4 |Keep a hash-chained trail of every check | `open_log("audit.db")` |

## Evidence from realistic evaluations

Evaluations on agentic systems built for real regulatory and benefits workloads show a consistent pattern when tools are configured for the domain and tiers are matched:

**Where the deterministic stack is strong**

| Configuration | Model calls | Recall on defects | False alarms | Stability |
|---------------|-------------|-------------------|--------------|-----------|
| Groundlens rules (domain-configured) | 0 | 0.84 | 0.00 | exact |
| Groundlens rules + geometry | 0 | up to 0.93 | 0.00 | exact |
| Rules on lookup defects (fabricated citation, number in no source, non-existent document) | 0 | 1.00 | 0.00 | exact |

Rules catch lookup defects in milliseconds with bit-exact reproducibility. Geometry separates answers that ignore the source from answers that engage it (AUROC in the low-to-mid 0.8s on that class). Two of the three most complete evaluations recommend adopting Groundlens for the output surface, in combination with other controls.

**Limits of Groundlens**

- Geometry is weak on local factual edits that keep the correct register and change only a value or an actor. On that class it has been near chance; simple baselines can match it.
- Rules only catch what they are written to catch. Classes that need reading (calculation contradictions, application of a legal test the scheme does not contain) are better handled by a judge.
- Under a fixed review budget, adding a second signal with higher false-alarm rate can reduce the number of true defects that reach a human. Complementarity as set overlap is not the same as net value under cost.
- Out-of-the-box thresholds and the default DGI direction are fitted on particular corpora. Production use requires calibration on your data.

More details about Groundlens limits can be found in [BENCHMARKS.md](BENCHMARKS.md).


## Install

```bash
pip install groundlens
```

## Encoder and offline use

The geometric stages (SGI/DGI) use a sentence encoder. The default is `sentence-transformers/sentence-t5-large` (~640 MB). On first use it is downloaded once from Hugging Face and cached locally. After that, scoring is fully local: no text is sent anywhere, and there is no telemetry. The test suite includes a socket monitor that fails if a scoring call opens an outbound connection.

**Rules and the Switch use no encoder.** You can run those stages with zero model weights.

### Offline / air-gapped

1. On a connected machine, download the encoder once:

```bash
huggingface-cli download sentence-transformers/sentence-t5-large \
  --local-dir ./encoders/sentence-t5-large
```
2. Ship that directory with your app (image layer, internal registry, artefact store). Prefer your own artefact store over committing weights to git.
On the target host, point at the local path and disable Hub access:

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

```Python
from groundlens import compute_sgi

result = compute_sgi(
    question=q,
    context=ctx,
    response=a,
    model="/path/to/encoders/sentence-t5-large",  # local directory
)
```

3. You can also set a process-wide default with `set_default_encoder(...)` (see [Docs](https://docs.groundlens.dev)).

### Optional alternatives

|Option| When to use it|
|---|---|
|Smaller encoder (all-MiniLM-L6-v2, all-mpnet-base-v2, …) | To reduce latency and size constraints. (*Important note: if you want to recalibrate thresholds, consider that different embedding spaces are not interchangeable*)|
|Rules-only| If you need lookup and policy defects only|
|Private mirror / internal registry| When you want controlled provenance and availability inside your network|

## Quick start

### Source-grounded check (RAG)

```python
from groundlens import compute_sgi, check

result = compute_sgi(
    question="What is the current heating-allowance rate?",
    context=retrieved_document,
    response=llm_answer,
)
reading = check(result)
print(reading.level)      # "ok" | "review" | "risk"
print(reading.escalate)
print(reading.render())
```

When retrieval returns several chunks, score each separately and keep the best:

```python
best = max(
    (compute_sgi(question=q, context=chunk, response=a) for chunk in chunks),
    key=lambda r: r.value,
)
```

### No-source check (eg. one-shot promting)

```python
from groundlens import compute_dgi, check

result = compute_dgi(question=question, response=answer)
reading = check(result)
```

### Policy and completeness rules

```python
from groundlens.rules import decision_rationale_rules

result = decision_rationale_rules(domain="finance").evaluate(
    question=question,
    response=answer,
    metadata={"entities": extracted_entities, "schema": tool_schema},
)
print(result.flagged, result.audit_explanation)
```

Agent rule packs expect dialogue context, captured entities and an operation schema. Called without them they abstain. Supply what a real deployment would supply.

### Agent state gate

```python
from groundlens import GroundingSwitch, compute_sgi

score = compute_sgi(question=q, context=src, response=a)
decision = GroundingSwitch(on_reject="reject").decide(score)
print(decision.write_to_state)
```

### Audit trail

```python
from groundlens.audit import open_log

with open_log("audit.db") as log:
    log.record(
        identifier="case-4471",
        method="sgi",
        flagged=result.flagged,
        score=result.value,
        inputs={"question": question},
    )
    print(log.verify_chain().valid)
```


## Calibration and thresholds

Thresholds and the DGI reference direction are configuration, not constants. Fit them to your data.

```python
from groundlens import fit_thresholds, DGI

# Label 1 = ungrounded (should escalate), 0 = grounded
examples = [
    {"question": q1, "response": r1, "label": 0, "context": src1},
    {"question": q2, "response": r2, "label": 1},
]
fit = fit_thresholds(examples)

scorer = DGI()
scorer.calibrate(pairs=grounded_pairs)  # only the grounded ones for the reference direction
```

If DGI flags everything, the reference direction is wrong for your style; lowering the threshold will not fix it. Re-estimate the direction. If agent rules pass everything, check that dialogue, entities and schema were actually passed. Full details: [calibration](https://docs.groundlens.dev/concepts/calibration/).


## Audit tools

```python
from groundlens.audit import open_log

with open_log("audit.db") as log:
    log.record(
        identifier="ticket-4471",
        method="sgi",
        flagged=result.flagged,
        score=result.value,
        inputs={"question": question},
    )
    print(log.verify_chain().valid)
```

Every entry is hashed against the one before it. The chain answers two questions: whether the record was altered, and whether the verdict can be recomputed from corpus version and detector build.


## Agentic pipelines  integrations

LangChain · LangGraph · CrewAI · Semantic Kernel · AutoGen · OpenAI · Anthropic · Gemini · Hugging Face — [integrations](https://docs.groundlens.dev/integrations/).

MCP server for Claude Desktop, Cursor and Windsurf: [groundlens-mcp](https://github.com/groundlens-dev/groundlens-mcp).


## Open core and the hard production pieces

This repository is the open core under Apache-2.0.

The pieces that usually matter for production and for regulated deployments are not all inside a `pip install`:

- pinned, versioned encoders that do not change under you,
- maintained domain rule packs and canary tests that assert known-bad answers fail,
- compliance evidence packs (test metrics, thresholds, logging schema, monitoring) that map to the obligations you actually have,
- integration templates for LangGraph and similar agent frameworks with stage ordering and audit already wired,
- a hosted path when you cannot or do not want to run the encoder in-process.

For these jobs, you can contact javier@groundlens.dev

## Research

| # | Paper | ID |
|---|-------|-----|
| 1 | Semantic Grounding Index: Geometric Bounds on Context Engagement in RAG Systems | [arXiv:2512.13771](https://arxiv.org/abs/2512.13771) |
| 2 | A Geometric Taxonomy of Hallucination in LLMs | [arXiv:2602.13224](https://arxiv.org/abs/2602.13224) |
| 3 | How Transformers Reject Wrong Answers | [arXiv:2603.13259](https://arxiv.org/abs/2603.13259) |
| 4 | The Outer Geometry of Truth | preprint |
| 5 | The Geometry of Validity | preprint |


## Citation

```bibtex
@software{marin_groundlens,
  author  = {Marin, Javier},
  title   = {Groundlens: deterministic first-stage verification for LLM and agent outputs},
  url     = {https://github.com/groundlens-dev/groundlens},
  license = {Apache-2.0}
}
```

## Contributing

Issues and pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).  

Contact; javier@groundlens.dev

