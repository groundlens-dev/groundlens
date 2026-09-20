<div align="center">

![GroundLens](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/groundlens_header.png)

## Execution verification runtime for AI systems and agents

<br>

[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

[![PyPI](https://img.shields.io/pypi/v/groundlens?color=1a4fd6)](https://pypi.org/project/groundlens/)
[![Rust](https://github.com/groundlens-dev/groundlens/actions/workflows/rust.yml/badge.svg)](https://github.com/groundlens-dev/groundlens/actions/workflows/rust.yml)
[![Python](https://github.com/groundlens-dev/groundlens/actions/workflows/python.yml/badge.svg)](https://github.com/groundlens-dev/groundlens/actions/workflows/python.yml)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13390/badge)](https://www.bestpractices.dev/projects/13390)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/groundlens-dev/groundlens/badge)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)
[![REUSE status](https://api.reuse.software/badge/github.com/groundlens-dev/groundlens)](https://api.reuse.software/info/github.com/groundlens-dev/groundlens)
[![SLSA](https://slsa.dev/images/gh-badge-level2.svg)](https://slsa.dev/images/gh-badge-level2.svg)

<br>

[What it is](#what-groundlens-is) · [What it verifies](#what-groundlens-verifies) · [Beside your system](#beside-your-system-not-inside-it) · [How it works](#how-it-works) · [Verifiers](#verifiers) · [Gating tool calls and actions](#gating-tool-calls-and-actions) · [Policies](#policies) · [Evidence records](#every-check-leaves-a-record) · [Quick start](#quick-start) · [Determinism](#determinism) · [Examples](#examples) · [FAQ](https://github.com/groundlens-dev/groundlens/blob/main/FAQ.md) · [Roadmap](https://github.com/groundlens-dev/groundlens/blob/main/ROADMAP.md)

</div>

<br>

## What GroundLens is

GroundLens is an execution verification runtime for AI systems and agents. It turns observable AI execution into deterministic, policy-governed evidence that can be independently verified.

GroundLens provides a vendor-neutral runtime and evidence protocol for observing AI executions, evaluating claims, tool calls, actions and outcomes against composable verifiers and policies, and producing signed, reproducible evidence records.

An AI system, and increasingly an agent, does things an organisation is accountable for: it answers, it retrieves, it calls tools, it takes actions with consequences. When one of those is later questioned, by a customer, a risk officer or an auditor, the organisation has to show four things: what happened, what was checked, under which rules, and whether the same check gives the same result today. A score in a log cannot show that, and a system cannot vouch for itself.

GroundLens is the layer that shows it. It watches what an AI system produces and does, runs independent checks against the rules you wrote, and seals the whole thing into a signed record a third party can verify offline, without trusting you. It runs locally, needs no access to your weights, prompts or architecture, and treats every check as evidence someone can inspect rather than a number they have to believe.

<br>

| Best for teams | Standout |
|---|---|
| Shipping AI answers and agents into regulated or high-stakes workflows who need proof, not a score, that each output and each action was checked. | Answers and executions verified under one contract; composable verifiers (exact numeric and rule checks, lexical grounding, and more); an execution policy that gates tool calls and actions `ALLOW` / `REVIEW` / `DENY`; policies in YAML that decide instead of hard-coded thresholds; signed, hash-chained records verifiable offline; the engine and runtime never touch the network. |

<br>

## What GroundLens verifies

The unit is the execution. An execution is an ordered sequence of steps: a model is called, documents are retrieved, a tool is requested and returns, an action with side effects runs, a human approves. GroundLens records each step as an event in a hash-linked log, checks it, and reaches a decision.

Verifying a single answer is the smallest case, a run with one claim, so one contract covers both ends of the range:

- an **answer**, and the claims inside it, gets `PASS`, `REVIEW` or `FAIL` from verifiers and a policy;
- a **tool call or an action** gets `ALLOW`, `REVIEW` or `DENY` from an execution policy.

Either way the run is sealed into a signed, chained record. What the record keeps of the world is hashes, not content, so it is safe to hold in a regulated place while staying independently verifiable.

<br>

## Beside your system, not inside it

<div align="center">

![Where GroundLens sits](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/diagram_layer.png)

</div>

GroundLens sits next to your AI system. It observes what the system produces and does, and the evidence around it, and never sees your weights, your prompts or your internal architecture, so independent verification is possible even in a bank or a sensitive deployment.

It reads a run from what an agent already emits. An agent driving its tools speaks the Model Context Protocol (MCP): the JSON-RPC messages it exchanges to call a tool and read the result. GroundLens ingests those messages and turns them into a run, recording hashes of the arguments and results, never the content itself. Recording a run needs no change to how the agent is built.

<br>

## How it works

<div align="center">

![How a verification works](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/diagram_pipeline.png)

</div>

<br>

| Verifier | Policy |
|---|---|
| A verifier produces evidence, not truth. Exact numeric checks, lexical grounding, semantic similarity, NLI, the geometric SGI and DGI indices, symbolic rules, your own verifiers and, if you allow it, an LLM judge: each one reports what it measured and how sure it is. None of them decides. | A policy interprets the evidence. A short YAML file you control says which verifiers are required, recommended, optional or forbidden, what thresholds apply, and how evidence becomes a decision. It can map each outcome to the governance or regulatory control it concerns, such as an article of the EU AI Act. |

The whole chain becomes a record: the input hashes, the verifiers and model hashes that ran, the evidence, the policy and its hash, the decision, the regulatory mapping, and the hash of the previous record, sealed with an Ed25519 signature. A log of records is an audit trail you can hand over as a file.

<br>

> GroundLens is AI system agnostic. It works on outputs, executions and evidence, locally. The engine and the runtime never touch the network, so independent verification is possible even in sensitive environments. The one network operation in the whole project is a single explicit command, `bundle pull`, which fetches the optional lexical model and nothing else.

<br>

## Engine and runtime

The engine and runtime are a Rust workspace under `crates/`, wrapped for Python, with no runtime dependencies. They hold the claim extractor and verifiers, the numerals-and-units machinery, the policy engine, the signed evidence records, and the execution runtime: the event log, the execution policy gate and the MCP adapter. The Python package is a thin binding over them; `glv` is the same code as a binary.

The distinction matters for a regulated deployment: **no engine or runtime crate depends on an HTTP or TLS library, and a CI job fails the build if one ever does.** The network belongs only to the command line, in one explicit artefact-acquisition step, `bundle pull`. Verification itself never reaches the network.

```bash
cargo build --release                 # engine, runtime and glv
cd python && maturin build --release  # Python wheel
```

<br>

## Verifiers

These verifiers examine an **answer** and the claims inside it. What an agent **did**, its tool calls and actions, is decided by the execution policy in [Gating tool calls and actions](#gating-tool-calls-and-actions).

| verifier | what it does | guarantee | in `pip install` |
|---|---|---|---|
| `groundlens.numeric` | numbers, currencies, percentages and physical units, compared exactly in base units: `1.2 km` equals `1200 m`, `212 °F` equals `100 °C`, `$37.35 billion` equals a table cell `37,350` under "in millions of dollars" | exact, bit-identical everywhere | yes |
| `groundlens.rules` | your own symbolic rules (an APR must be a percentage, a date must fall inside the contract term) | exact | yes |
| `groundlens.lexical` | whether each word of the answer is anchored in the sources, by contextual token similarity on a frozen multilingual encoder, reported as the weakest anchor rather than an average | reproducible: pinned model hash, scores within 1e-6 across machines | with the base bundle |
| NLI, semantic, SGI, DGI, LLM judge | entailment, meaning, geometric grounding and model-based judgement | optional verifiers, see the [roadmap](https://github.com/groundlens-dev/groundlens/blob/main/ROADMAP.md) | later releases |

Locales matter for numbers: `1.234` is one thousand in Spanish and one and a bit in English. GroundLens reads `en`, `es`, `ca`, `de`, `fr`, `it`, `pt`, `nl` and Swiss formats, knows short and long scale words, and keeps every legitimate reading of an ambiguous numeral instead of guessing. The base bundle's encoder covers about a hundred languages.

<br>

## Gating tool calls and actions

An execution policy decides what an agent is allowed to do. It is a short, ordered list of rules; each rule matches a tool call or an action and carries an effect. `DENY` stops the step, `REVIEW` holds it for a human, `ALLOW` lets it proceed. The first rule that matches decides, and when none does the policy's default applies, so a conservative deployment denies anything it did not explicitly allow.

```yaml
id: eu_high_risk_v1
rules:
  - id: no-shell          # a shell tool is never allowed, from any server
    match: tool
    name: shell.exec
    effect: DENY
  - id: high-risk         # any action at or above high risk needs a human
    match: risk_at_least
    risk: high
    effect: REVIEW
default: ALLOW
```

After a run, GroundLens audits the whole log against the policy and rolls it up to a single verdict. It flags any action that ran against the policy: one the policy forbade, or one that needed a human approval that never came. The verdict and the breaches go into the signed record, so an auditor can replay a run and see whether the policy was actually honoured. The gate is pure rule matching, with the same `exact` guarantee as the numeric verifier.

<br>

## Policies

A policy is a short YAML file. Two policies over the same evidence can reach different decisions, and both are correct: that is where your risk appetite lives, not in the engine.

```python
record = verify(answer, sources, policy="eu_ai_act_high_risk_v1")
record.decision              # 'FAIL'
record.regulatory_mapping    # [{'article': 'Art. 15(1)', ...}, {'article': 'Art. 12(1)', ...}]
```

The bundled `eu_ai_act_high_risk_v1` policy maps outcomes to Art. 15(1) (accuracy and robustness) and Art. 12(1) (record keeping) of Regulation (EU) 2024/1689. Write your own with `Policy.from_yaml()`; every policy has a version and a hash, and the hash goes into every record it decides.

```yaml
id: acme_rag_v1
version: 1.0.0
verifiers:
  required: [groundlens.numeric, groundlens.lexical]
  forbidden: [llm_judge.*]
thresholds:
  groundlens.lexical: { support_min: 0.60, guard_band: 0.02 }
decision:
  any_contradiction_from: [groundlens.numeric, groundlens.rules.*]
  unresolved_claims: REVIEW
```

Scores from statistical verifiers drift slightly between machines, so every threshold carries a guard band: a score inside the band is `REVIEW` everywhere, never `PASS` on one laptop and `FAIL` on another. `groundlens policy lint` refuses a band narrower than the verifier's declared tolerance.

<br>

## Every check leaves a record

Whether GroundLens checked one answer or a whole run, the result is the same kind of artefact: a signed record, chained to the one before it, that anyone can verify offline.

```python
record.content_hash     # same input, policy and bundle → same hash, on any machine
record.verify()         # recompute every hash and the Ed25519 signature, offline
Record.verify_chain(Record.read_log("records.jsonl"))
```

Change one byte anywhere in a record and verification fails. Append records to a JSON Lines log and each one carries the hash of the previous one. `groundlens report` turns a log into a human-readable report with a one-page guide for auditors.

<br>

## Quick start

```bash
pip install groundlens     # installs the GroundLens engine and runtime
```

**Verify an answer** against its sources under a policy.

```python
from groundlens import verify

question = "What is the invoice total?"
source = "...the total amount due is 10,000 dollars, payable within 30 days..."
answer = "The invoice total is 1,000 dollars, due in 30 days."

record = verify(answer, [("invoice.pdf#p1", source)], question=question)
print(record.report())
```

```
FAIL  policy=groundlens_default_v1  record=rec_350455f44e60_4dbfea8eb79c
  c2   groundlens.numeric       contradicted  0.00  nearest in invoice.pdf#p1: '10,000 dollars'
```

Ten is not a hundred. A similarity score would rate the right answer and the wrong one alike; the numeric verifier compares the quantities exactly and points at the source passage the number lost to.

**Verify a run.** Give GroundLens an MCP execution trace and an execution policy; it seals a signed run record and tells you what the policy decided.

```python
from groundlens import verify_run

record = verify_run(trace, policy, run_id="run_demo", system="invoice-agent")
record.gate        # 'DENY'  — the agent called a tool the policy forbids
record.breaches    # any action executed against the policy
```

```bash
glv run verify --trace examples/run/trace.jsonl --policy examples/run/execution-policy.yaml \
  --run-id run_demo --system invoice-agent --log runs.jsonl
glv run check runs.jsonl        # every hash, every link, every signature, offline
```

A runnable version of both is under [`examples/run`](examples/run).

---

`groundlens bundle pull base` is a separate, explicit step.

```bash
groundlens bundle pull base      # optional: enables the lexical verifier (≈470 MB, once)
```

It downloads the **base bundle** (about 470 MB: the multilingual-e5-small encoder in f32, its tokenizer and a manifest of hashes) from this repository's releases into a per-user directory, checks it against a hash pinned in the engine, and refuses anything else. It is the only command in the package that opens a network connection. With the bundle installed, the **lexical** verifier runs and every record names the bundle by hash. In an isolated environment, copy the bundle directory by hand and point `GROUNDLENS_BUNDLE_DIR` at it.

---

The command line. Everything here except the lexical verifier works with the base install alone. Nothing leaves your machine.

```bash
groundlens verify --answer answer.txt --question question.txt \
  --source "invoice.pdf#p1=invoice.txt" --policy eu_ai_act_high_risk_v1 --log records.jsonl
groundlens record verify records.jsonl        # every hash, every link, every signature
groundlens report records.jsonl --out report  # report.md, report.json, README-auditor.md
groundlens policy lint policies/eu_ai_act_high_risk_v1.yaml
groundlens bundle status                      # is the base bundle installed, where, which hash
```

Exit codes: `0` PASS, `1` FAIL, `2` error, `3` REVIEW. The Rust binary `glv` exposes the same commands and adds execution verification: `glv run verify` seals an agent run (exit `0` / `3` / `1` on `ALLOW` / `REVIEW` / `DENY`) and `glv run check` verifies a log of run records offline.

<br>

## Determinism

Same input, same result, on any machine.

Each verifier declares what it guarantees. `exact` verifiers, and the execution gate, use no floating point at all. `reproducible` verifiers run a pinned model, in f32, on a pure-Rust inference engine, and their scores stay within a declared tolerance. Anything `non_deterministic`, such as an LLM judge, is recorded with its model, prompt hash and settings, and only decides if the policy says so.

This is tested rather than promised: the CI runs the invoice example, with and without the lexical channel, on Linux, macOS and Windows under a Turkish locale and a Pacific timezone, and compares the record hash with a committed value.

<br>

## Examples

Two notebooks under [`examples/notebooks`](examples/notebooks) run in Google Colab:

- **Verify an AI answer against its sources**: one example in English, German, French, Spanish and Italian, from `pip install` to a signed record, with a wrong number, a paraphrase and a policy change.
  <a target="_blank" href="https://colab.research.google.com/github/groundlens-dev/groundlens/blob/main/examples/notebooks/01_verify_an_answer_in_five_languages.ipynb">
  <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/>
</a>

- **Evidence records for auditors**: a log of verifications, chain verification, tamper detection, the EU AI Act mapping and the report an auditor receives.
  <a target="_blank" href="https://colab.research.google.com/github/groundlens-dev/groundlens/blob/main/examples/notebooks/02_evidence_records_for_auditors.ipynb">
  <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/>
</a>

And a shell example of a whole agent run under [`examples/run`](examples/run): a trace, an execution policy and a signed run record.

<br>

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

<div align="center">

[groundlens.dev](https://groundlens.dev) · Javier Marín, 2026 (javier@groundlens.dev)

</div>
