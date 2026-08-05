<div align="center">

# Groundlens

### Checks for the output of language models and agents.

**No generative model in the scoring path.** Geometry uses a sentence encoder, not an LLM; Switch and Rules use no model at all. Deterministic, local, the same answer every time. One stage, Consistency, loads a small local generator, and only for the answers the cheaper stages could not settle.

[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13%20|%203.14-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![PyPI](https://img.shields.io/pypi/v/groundlens?style=flat-square&label=version&color=orange)](https://pypi.org/project/groundlens/)
[![Downloads](https://img.shields.io/pepy/dt/groundlens?style=flat-square&label=downloads&color=orange)](https://pepy.tech/project/groundlens)
[![License: Apache](https://img.shields.io/badge/license-Apache%202-green?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/groundlens-dev/groundlens?style=flat-square&label=OpenSSF%20Scorecard)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![Demo](https://img.shields.io/badge/demo-HuggingFace-yellow?style=flat-square)](https://huggingface.co/spaces/groundlens/demo)

</div>

```bash
pip install groundlens
```

---

<div align="center">
<img src="docs/assets/pipeline.png" alt="Six stages, cheapest first. Groundlens is stages 1 to 4: Geometry, Switch, Consistency, Rules. You add stages 5 and 6: an LLM judge and a human reviewer." width="100%">
</div>

**Verification is a pipeline, ordered cheapest first.** Groundlens is stages 1 to 4. They settle what they can and pass only the doubtful cases forward, so an LLM judge or a human reviewer only ever sees what is actually in doubt.

*Funnel percentages in the diagram are illustrative. Yours depend on your data, and `groundlens evaluate` on a labelled sample will tell you what they actually are.*

---

## The tools

| | Use it to | Call |
|---|---|---|
| **SGI** | Check an answer against the source it was given | `compute_sgi(question, context, response)` |
| **DGI** | Check an answer when there is no source. Calibrate it first | `compute_dgi(question, response)` |
| **Check** | Turn any score into a plain-language reading | `check(score)` |
| **Switch** | Decide whether an answer may be written into agent state | `GroundingSwitch().decide(score)` |
| **Consistency** | Ask the model again and measure whether it agrees with itself | `two_stage(question, answer, model=...)` |
| **Rules** | Check an answer against a written policy, with evidence | `groundlens.rules.decision_rationale_rules()` |
| **Calibrate** | Fit the cut points to your own data instead of ours | `fit_thresholds(examples)` |
| **Audit** | Keep a hash-chained trail of every check you ran | `open_log("audit.db")` |

Some of it from the shell too:

```bash
groundlens check --question "..." --context "..." --response "..."
groundlens evaluate pairs.csv --output results.csv
groundlens calibrate --pairs pairs.csv --output calibration.json
groundlens doctor
groundlens benchmark
```

**Where they sit.** Verification is a pipeline ordered cheapest to most expensive. These are the cheap end: they settle the obvious cases so an LLM judge or a human reviewer only ever sees what is actually doubtful.

---

## SGI — did the answer come from the source?

```python
from groundlens import compute_sgi

result = compute_sgi(question=question, context=source_document, response=answer)
print(result.value, result.flagged)
```

SGI is the ratio of two angles: how far the answer sits from the question, over how far it sits from the source. High means the answer moved toward the source, which is what an answer drawn from it looks like.

| at or above 1.20 | 0.95 to 1.20 | below 0.95 |
|---|---|---|
| came from the source | partly grounded | did not come from the source |

The middle band is what to escalate. Geometry cannot settle it alone.

**Which field is the decision?** `result.flagged` is the single hard cut at 0.95, so it is `False` for the whole middle band. For the escalate-this set, use `check()`:

```python
from groundlens import check, compute_sgi

result = compute_sgi(question=question, context=source_document, response=answer)
reading = check(result)
print(reading.level)      # "ok" | "review" | "risk"
print(reading.escalate)   # True for the middle band as well as the red one
print(reading.render())   # the same thing in a sentence
```

Branch on `check(result).escalate`. Branching on `result.flagged` silently passes every answer geometry could not settle.

**Grounding is not truth.** A wrong fact phrased in the right frame will pass. SGI tells you where an answer came from, not whether it is correct.

### What to pass as `context` when retrieval returns several chunks

Score each chunk separately and keep the best. An answer is grounded in *a* source, not in the average of five.

```python
from groundlens import compute_sgi

best = max(
    (compute_sgi(question=question, context=chunk, response=answer) for chunk in chunks),
    key=lambda r: r.value,
)
```

Concatenating the chunks moves the context embedding toward the average of several topics, which pushes `ctx_dist` up for all of them and depresses SGI even when the answer tracks one chunk exactly.

Two things to watch. The encoder truncates long inputs, so a chunk much beyond a few hundred words is only partly scored: keep chunks at retrieval size rather than pasting whole documents. And when question and context are near-identical, which is what good retrieval produces, both angles get small and their ratio gets noisy. `result.q_dist` and `result.ctx_dist` are on the result object so you can see when that is happening.

### One number to know about

An answer copied verbatim from the source returns `10.0` with `flagged=False`. That is a saturation sentinel, not a measurement: `ctx_dist` is zero and the ratio is undefined. SGI is maximised by quoting, so it rewards extraction. If your system is meant to synthesise rather than quote, a wall of 10.0s is a finding about your generator, not a clean bill of health.

## DGI — no source available

```python
from groundlens import compute_dgi

result = compute_dgi(question=question, response=answer)
```

For one-shot prompting, tool use, or an agent talking to itself. DGI compares the direction from question to answer against a reference direction learned from a corpus of grounded answers.

**Calibrate it before you rely on it.** The shipped reference direction is the mean displacement of 212 answers written in one style. Text written any other way scores low however faithful it is — a freshly written grounded answer measures 0.12 to 0.22 against a shipped cut of 0.525. The cut applies to the corpus it came from. Fit your own:

```python
from groundlens import DGI

scorer = DGI()
scorer.calibrate(pairs=my_grounded_pairs)      # list of (question, response)
result = scorer.score(question=question, response=answer)
```

That fixes the *direction*. If your escalation rate is wrong but the direction is fine, it is the *cut* you want — see [Calibrate](#calibrate--fit-the-cut-points-to-your-data).

Where a source exists, prefer SGI.

## Switch — may this answer enter state?

```python
from groundlens import GroundingSwitch, compute_sgi

score = compute_sgi(question=question, context=source_document, response=answer)
decision = GroundingSwitch(on_reject="reject").decide(score)

print(decision.write_to_state)   # may this answer enter state?
print(decision.action)           # what to do when it may not
print(decision.reason)
```

In an agent loop, one bad answer written into state contaminates every turn after it. Switch turns a score into that decision.

## Consistency — does the model agree with itself?

```python
from groundlens.verify import two_stage

result = two_stage(question=question, answer=answer, model="Qwen/Qwen2.5-0.5B-Instruct")
print(result.escalated, result.final.render())
```

Needs `pip install "groundlens[verify]"`, which brings transformers and torch. This is the one stage that loads a generative model, and `two_stage` only reaches it when the cheap stages could not settle the answer.

When there is no source to check against, resample the model and measure agreement. This is the one stage that needs a model, and it only runs on what the earlier stages could not settle.

## Rules — did it break a policy?

```python
from groundlens.rules import decision_rationale_rules

result = decision_rationale_rules(domain="finance").evaluate(
    question=question, response=answer, metadata=metadata
)
print(result.checks_passed, result.flagged)
print(result.audit_explanation)
```

Deterministic checklists for regulated settings: invented figures, missing disclosures, unsupported causal claims. Every result carries the text that triggered it.

**Rules are pattern checks, not measurements.** `checks_passed` is a weighted count of patterns that matched, not a probability of anything. Text with the right words in the right order will score well whether or not it is correct. Rules live under `groundlens.rules` rather than the top level for that reason, and the module docstring lists the four limits worth knowing before you rely on them.

## Calibrate — fit the cut points to your data

Two knobs, and they fix different problems.

```python
from groundlens import fit_thresholds

# one dict per answer. label 1 = ungrounded, 0 = grounded.
# context is optional and only needed if you also want an SGI cut.
examples = [
    {"question": q1, "response": r1, "label": 0, "context": src1},
    {"question": q2, "response": r2, "label": 1},
    # ... a few hundred of these
]
fit = fit_thresholds(examples)
print(fit.dgi_pass, fit.sgi_review, fit.in_sample)
```

**Label 1 means ungrounded.** Backwards does not raise, it silently fits inverted thresholds.

`fit_thresholds` moves the **cut**. `DGI().calibrate(pairs=...)` moves the **reference direction**. If DGI flags everything you write, it is the direction — a lower threshold on a compass pointing the wrong way does not help.

Our constants were fitted on our corpus. Yours will differ. A few hundred labelled answers is enough.

## Audit — keep the trail

```python
from groundlens import compute_sgi
from groundlens.audit import open_log

result = compute_sgi(question=question, context=source_document, response=answer)

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

Every entry is hashed against the one before it, so a modified record breaks the chain and `verify_chain()` says so. SQLite, local, no service.

---

## Batch, integrations and the MCP server

```python
from groundlens import evaluate_batch
rows = evaluate_batch(items)
```

LangChain · LangGraph · CrewAI · Semantic Kernel · AutoGen · OpenAI · Anthropic · Gemini · Hugging Face — see [integrations](https://docs.groundlens.dev/integrations/).

The same checks inside Claude Desktop, Cursor and Windsurf: [**groundlens-mcp**](https://github.com/groundlens-dev/groundlens-mcp).

## Install notes

First run downloads the default encoder, `sentence-transformers/sentence-t5-large`, about 640 MB. After that everything runs locally on CPU. `sentence-transformers` brings `torch`, so expect a large install. Smaller encoders are supported — see [installation](https://docs.groundlens.dev/getting-started/installation/).

## Privacy

Nothing leaves your machine. Scoring is local, there is no telemetry, and no text is sent anywhere. A test in the suite opens a socket monitor and fails if scoring makes a single outbound connection. See [DATA_HANDLING.md](DATA_HANDLING.md).

## What these tools cannot do

Every metric here ships with its measured ceiling and its failure modes, and earlier published numbers that did not hold have been withdrawn. Read [the benchmarks page](https://docs.groundlens.dev/benchmarks/results/) before quoting a figure, and the [project overview](https://github.com/groundlens-dev) for what we corrected and why.

## Papers

[arXiv:2512.13771](https://arxiv.org/abs/2512.13771) · [arXiv:2602.13224](https://arxiv.org/abs/2602.13224) · [arXiv:2603.13259](https://arxiv.org/abs/2603.13259). Preprints, not peer reviewed.

## How to cite

```bibtex
@software{marin_groundlens,
  author  = {Marin, Javier},
  title   = {Groundlens: checks for the output of language models and agents},
  url     = {https://github.com/groundlens-dev/groundlens},
  license = {Apache-2.0}
}
```

See [CITATION.cff](CITATION.cff).

## Contributing

Issues and pull requests welcome. If you think a number here is wrong, open an issue with the reproduction — corrections get fixed and credited in the commit. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
