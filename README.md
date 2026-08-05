<div align="center">

# Groundlens

### Open tools for verifying the output of language models and agents.

Geometric metrics, rule sets, calibration, and an MCP server. Deterministic, no generative model in the scoring path, milliseconds per call.

[![PyPI](https://img.shields.io/pypi/v/groundlens?style=flat-square&label=version&color=orange)](https://pypi.org/project/groundlens/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-groundlens.dev-green?style=flat-square)](https://docs.groundlens.dev)
[![Demo](https://img.shields.io/badge/demo-HuggingFace-yellow?style=flat-square)](https://huggingface.co/spaces/groundlens/demo)

</div>

---

## What is in the set

| Tool | What it answers | What it needs |
|---|---|---|
| **SGI** · Semantic Grounding Index | Did the answer come from the source it was given? | a question, a source, an answer |
| **DGI** · Directional Grounding Index | Does the answer move in the direction grounded answers move for this kind of question? | a question and an answer, plus calibration on your own domain |
| **Switch** | May this answer be written into agent or RAG state? | an SGI or DGI score |
| **Consistency** | With no source available, does the model agree with itself? | a small open model |
| **Rules** | Did the answer break a policy, invent a number, skip a disclosure? | a rule set |
| **Calibration** | What are the right cut points for *my* data? | a few hundred of your own answers |
| **MCP server** | The same checks inside Claude Desktop, Cursor or Windsurf | [groundlens-mcp](https://github.com/groundlens-dev/groundlens-mcp) |

The two metrics answer different questions and the difference matters.

**SGI measures grounding.** There is a source, and SGI measures how far the answer moved toward it. The word grounding is doing real work: the source is the ground.

**DGI measures alignment.** There is no source. DGI compares the direction from question to answer against the direction grounded answers usually take. It is closer to a Directional *Alignment* Index, and the name is historical: it is the name in the papers. Use it where no source exists, and calibrate it on your own domain first. See [Calibrate DGI before you trust it](#calibrate-dgi-before-you-trust-it).

## The verification pipeline

You have to verify every model call. You cannot afford to verify them all the expensive way.

Verification is a pipeline of **six stages, ordered cheapest to most expensive**. Each stage settles what it can and passes only the doubtful cases forward. **Groundlens is stages 1 to 4**, so the slow, costly stages only ever see the answers that were actually flagged.

<div align="center">
<img src="https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/pipeline.png" alt="Verification pipeline: Geometry, Switch, Consistency and Rules are Groundlens. LLM as judge and human review you add. Each stage filters what reaches the next." width="100%">
</div>

| Stage | Approach | The question it answers | Cost | Groundlens |
|---|---|---|---|---|
| 1 | **Geometry** | Did the answer come from its source, or drift off it? | no model · deterministic | Included |
| 2 | **Switch** | May this answer be written into agent or RAG state? | no model · deterministic | Included |
| 3 | **Consistency** | No source? Does the model agree with itself when asked again? | small open model · cheap | Included |
| 4 | **Rules** | Did it break a policy, invent a number, skip a disclosure? | deterministic | Included |
| 5 | **LLM as judge** | The hard cases that need real reasoning over the evidence. | frontier API · costs tokens | Not included |
| 6 | **Human review** | A person makes the final call. | costs a person | Not included |

Use it as triage at the front of the pipeline. Clear the obvious cases in milliseconds and escalate only what is flagged. Same coverage on every call, a fraction of the time and cost.

> **Grounding is not truth.** SGI tells you whether an answer came from the source it was given, not whether it is correct. A wrong fact phrased in the right frame will pass. That gap is why stage 3 exists.

## Quick setup

```bash
pip install groundlens
```

First run downloads the default encoder, `sentence-transformers/sentence-t5-large`, about 640 MB. After that everything runs locally on CPU. `sentence-transformers` brings `torch`, so expect a large install. For a smaller footprint see [choosing an encoder](https://docs.groundlens.dev/getting-started/installation/).

## SGI: did the answer come from the source?

```python
from groundlens import compute_sgi

question = (
    "How long does the Northwind warehouse keep a returned item before it is "
    "restocked, and who signs off on the inspection?"
)
context = (
    "Returned items arrive at the Northwind warehouse dock and enter a 14-day "
    "quarantine bay. During quarantine a floor supervisor inspects the item "
    "against the original packing slip. Only after the supervisor signs the "
    "inspection line does the item move to restocking; unsigned items are held "
    "past 14 days and escalated to the regional manager."
)

from_source = (
    "A returned item sits in the quarantine bay for 14 days. A floor supervisor "
    "checks it against the original packing slip and signs the inspection line; "
    "only then is it restocked. If nobody signs, it is held beyond the 14 days "
    "and goes to the regional manager."
)
not_from_source = (
    "Northwind restocks returned items the same afternoon they arrive, with no "
    "quarantine period at all. Inspection is fully automated, so no member of "
    "staff signs anything, and the regional manager is never involved."
)

print(round(compute_sgi(question=question, context=context, response=from_source).value, 2))
print(round(compute_sgi(question=question, context=context, response=not_from_source).value, 2))
```

```
1.77
1.04
```

SGI is a ratio of two angles. High means the answer sits closer to the source than to the question, which is what an answer drawn from the source looks like.

| SGI at or above 1.20 | SGI between 0.95 and 1.20 | SGI below 0.95 |
|---|---|---|
| 🟢 came from the source | 🟠 partly grounded | 🔴 did not come from the source |

The middle band is where geometry cannot settle it on its own. Those are the answers to escalate.

These examples are not drawn from the bundled reference set, so the numbers above are what the library produces on text it has never seen.

## DGI: alignment when there is no source

Sometimes there is no retrieved document: one-shot prompting, tool use, an agent talking to itself. DGI works from the question and the answer alone. It compares the direction the answer takes against a reference direction learned from a corpus of grounded answers.

```python
from groundlens import compute_dgi

print(round(compute_dgi(question=question, response=from_source).value, 3))
print(round(compute_dgi(question=question, response=not_from_source).value, 3))
```

```
0.124
0.031
```

The ordering is right and both numbers are low, because the reference direction shipped with the library was not built for warehouse logistics.

### Calibrate DGI before you trust it

This is the part to read before using DGI in anything that matters.

DGI's reference direction, μ̂, is the mean displacement of 212 grounded answers that ship with the library. Those answers were all generated by one model, in one style, answering textbook questions across nine domains. **μ̂ therefore encodes that corpus, not grounding in general.** Text written any other way points somewhere else and scores low no matter how faithful it is.

Measured on 2026-08-04 with the default encoder:

| Text | DGI |
|---|---|
| the 212 bundled reference answers | 0.2536 to 0.7609, median 0.5569 |
| a fresh warehouse answer, faithful to its source | 0.1235 |
| a fresh medical answer, faithful to its source | 0.2177 |
| `DGI_PASS`, the shipped cut | 0.5250 |

Medical is one of the nine domains the bundled corpus covers, and a freshly written medical answer still scores 0.2177. So the gap is not topic. It is authorship and register.

What follows is simple. **The shipped cut applies to the shipped corpus.** On your data, calibrate:

```python
from groundlens import fit_thresholds

# a few hundred of your own answers, labelled grounded / not grounded
fit = fit_thresholds(pairs=my_pairs)
print(fit.dgi_pass)     # the cut for your domain, not ours
```

On the bundled corpus, Youden's J puts the cut at 0.5236 against a shipped 0.5250, and AUROC at 0.7765. That figure is **in-sample**: μ̂ and the cut were both fitted on those same 212 pairs, so read it as evidence that the constant matches the corpus, not as an accuracy claim.

If you have a source available, prefer SGI. DGI is for when you do not.

## What the benchmarks give away for free

Before trusting any grounding detector, including this one, it is worth knowing how much of a benchmark score is not about grounding at all. These are measured, and reproducible on a laptop in under a minute.

| Benchmark | n | AUROC from claim length alone | AUROC from author identity alone |
|---|---:|---:|---:|
| RAGTruth | 2,700 | 0.664 | 0.720 |
| FaithBench | 800 | 0.590 | 0.615 |
| SummEdits | 6,348 | 0.510 | 0.565 |
| HaluEval | 20,000 | **0.972** | **1.000** |

On HaluEval, counting the words in the answer reaches 0.972. Knowing only who wrote it reaches 1.000, because the correct answers come from human-written corpora and the hallucinated ones were generated by a model. Authorship is the label.

SummEdits is what a carefully built benchmark looks like: every incorrect item is a minimal edit of a correct one, so length and authorship carry almost nothing.

Any detector reporting a high number on a confounded benchmark has to explain what it did that word-counting did not. That includes ours.

## What we withdrew

Earlier releases of this project published DGI figures around 0.958, a domain-calibrated range of 0.90 to 0.99, and an 87.8% detection rate. **Those numbers are withdrawn.** They were an authorship artifact: the grounded class was machine-written and the ungrounded class was human-written, so a detector could score highly by recognising who wrote the text.

We also previously described NLI methods as performing at chance in this setting. That was wrong. Natural language inference does not decline in-register and is the stronger method where you can afford it. Groundlens is the cheap first stage, not the best available detector.

Full detail in the [benchmarks page](https://docs.groundlens.dev/benchmarks/results/) and the [changelog](CHANGELOG.md).

We would rather publish the correction than the number.

## Switch: may this answer enter state?

In an agent loop, a bad answer that gets written into state contaminates every turn after it. `GroundingSwitch` turns a score into a decision.

```python
from groundlens import GroundingSwitch

switch = GroundingSwitch(on_reject="block")
decision = switch.decide(question=question, context=context, response=from_source)
print(decision.allowed, decision.reason)
```

## Consistency, rules and the rest

- **Consistency** resamples the model and measures whether it agrees with itself. Use it when there is no source to check against. See [two_stage](https://docs.groundlens.dev/concepts/two-stage/).
- **Rules** are deterministic checklists for regulated settings: invented figures, missing disclosures, unsupported causal claims. They are pattern checks, not measurements, and the docs say so.
- **Calibration** fits your own cut points with `fit_thresholds` and your own reference direction with `calibrate`.
- **Audit** writes a scored, timestamped trail of every check.

```bash
groundlens check --question "..." --context "..." --response "..."
groundlens calibrate --pairs my_pairs.csv
groundlens doctor
```

## Integrations

LangChain · LangGraph · CrewAI · Semantic Kernel · AutoGen · OpenAI · Anthropic · Gemini · Hugging Face.

```python
from groundlens.integrations.langchain import GroundlensEvaluator
```

See [integrations](https://docs.groundlens.dev/integrations/).

## MCP server

Run the same checks inside Claude Desktop, Cursor or Windsurf.

```bash
pip install groundlens-mcp
```

[groundlens-mcp](https://github.com/groundlens-dev/groundlens-mcp)

## Privacy

Nothing leaves your machine. Scoring is local, there is no telemetry, and no text is sent anywhere. A test in the suite opens a socket monitor and fails if scoring makes a single outbound connection. See [DATA_HANDLING.md](DATA_HANDLING.md).

## Papers

- **Semantic Grounding Index: Geometric Bounds on Context Engagement in RAG Systems** — [arXiv:2512.13771](https://arxiv.org/abs/2512.13771)
- **A Geometric Taxonomy of Hallucinations in Large Language Models** — [arXiv:2602.13224](https://arxiv.org/abs/2602.13224)
- **Rotational Dynamics of Factual Constraint Processing in Large Language Models** — [arXiv:2603.13259](https://arxiv.org/abs/2603.13259)

## How to cite

```bibtex
@software{marin_groundlens,
  author  = {Marin, Javier},
  title   = {Groundlens: open tools for verifying the output of language models and agents},
  url     = {https://github.com/groundlens-dev/groundlens},
  license = {Apache-2.0}
}
```

For the method itself, cite [arXiv:2512.13771](https://arxiv.org/abs/2512.13771). See [CITATION.cff](CITATION.cff).

## Working on verification at scale?

If you are checking generated output in a pipeline that matters, and paying for it in tokens or in people, I am interested in the problem. Calibration on your own domain is usually where the numbers start being useful.

**javier@groundlens.dev**

## Contributing

Issues and pull requests welcome. If you think a number here is wrong, open an issue with the reproduction — corrections get fixed and credited in the commit. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
