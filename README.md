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

[What it is](#what-groundlens-is) · [Architecture](#architecture) · [How it works](#how-it-works) · [Engine](#engine) · [Runtime](#runtime) · [Records](#evidence-records) · [Quick start](#quick-start) · [Determinism](#determinism) · [Examples](#examples) · [FAQ](https://github.com/groundlens-dev/groundlens/blob/main/FAQ.md) · [Roadmap](https://github.com/groundlens-dev/groundlens/blob/main/ROADMAP.md)

</div>

<br>

## What GroundLens is

GroundLens is an execution verification runtime for AI systems and agents. It turns observable AI execution into deterministic, policy-governed evidence that can be independently verified.

GroundLens provides a vendor-neutral runtime and evidence protocol for observing AI executions, evaluating claims, tool calls, actions and outcomes against composable verifiers and policies, and producing signed, reproducible evidence records.

The unit is the execution: an ordered sequence of steps an AI system or agent takes, from a model call and a retrieval to a tool call, an action with side effects and a human approval. GroundLens records each step, checks it, decides, and seals the run into a signed record anyone can verify offline. Verifying a single answer is the smallest case, a run with one claim.

- an **answer**, and the claims inside it → `PASS`, `REVIEW` or `FAIL`
- a **tool call or an action** → `ALLOW`, `REVIEW` or `DENY`

Where a guardrail blocks or scores an output in the moment and leaves nothing behind, GroundLens leaves signed, hash-chained evidence a third party can check without trusting you. It runs locally, needs no access to your weights, prompts or architecture, and is built for teams shipping AI answers and agents into regulated or high-stakes workflows who need proof, not a score.

<br>

## Architecture

<div align="center">

![Where GroundLens sits](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/diagram_layer.png)

</div>

GroundLens sits beside your AI system, not inside it. It observes what the system produces and does, and never sees your weights, your prompts or your internal architecture, so independent verification is possible even in a bank or a sensitive deployment.

It reads a run from what an agent already emits. An agent driving its tools speaks the Model Context Protocol (MCP); GroundLens ingests those JSON-RPC messages and turns them into a run, recording hashes of the arguments and results, never the content itself. Recording a run needs no change to how the agent is built.

The engine and runtime are a Rust workspace, wrapped for Python, with no runtime dependencies; `glv` is the same code as a binary. No engine or runtime crate depends on an HTTP or TLS library, and a CI job fails the build if one ever appears. The only network operation in the project is one explicit command, `bundle pull`, which fetches the optional lexical model. Verification never reaches the network.

<br>

## How it works

<div align="center">

![How a verification works](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/diagram_pipeline.png)

</div>

A verifier produces evidence, not truth: it reports what it measured and how sure it is, and none of them decides. A policy interprets the evidence and reaches the decision. The whole chain becomes a record: the input hashes, the verifiers and model hashes that ran, the evidence, the policy and its hash, the decision, the regulatory mapping, and the hash of the previous record, sealed with an Ed25519 signature. A log of records is an audit trail you can hand over as a file.

<br>

## Engine

The engine verifies an answer and the claims inside it. A verifier produces evidence; a policy turns it into `PASS`, `REVIEW` or `FAIL`.

| verifier | what it does | guarantee | in `pip install` |
|---|---|---|---|
| `groundlens.numeric` | numbers, currencies, percentages and physical units, compared exactly in base units: `1.2 km` equals `1200 m`, `212 °F` equals `100 °C`, `$37.35 billion` equals a table cell `37,350` under "in millions of dollars" | exact, bit-identical everywhere | yes |
| `groundlens.rules` | your own symbolic rules (an APR must be a percentage, a date must fall inside the contract term) | exact | yes |
| `groundlens.lexical` | whether each word of the answer is anchored in the sources, by contextual token similarity on a frozen multilingual encoder, reported as the weakest anchor rather than an average | reproducible: pinned model hash, scores within 1e-6 across machines | with the base bundle |

An entailment (NLI) verifier is in the codebase behind a feature flag and is not yet in the released wheel. Semantic, geometric (SGI, DGI) and LLM-judge verifiers are planned; see the [roadmap](https://github.com/groundlens-dev/groundlens/blob/main/ROADMAP.md). Every one plugs into the same contract.

Locales matter for numbers: `1.234` is one thousand in Spanish and one and a bit in English. GroundLens reads `en`, `es`, `ca`, `de`, `fr`, `it`, `pt`, `nl` and Swiss formats, knows short and long scale words, and keeps every legitimate reading of an ambiguous numeral instead of guessing. The base bundle's encoder covers about a hundred languages.

A policy is a short YAML file you control. Two policies over the same evidence can reach different decisions, and both are correct: that is where your risk appetite lives, not in the engine. The bundled `eu_ai_act_high_risk_v1` maps outcomes to Art. 15(1) (accuracy and robustness) and Art. 12(1) (record keeping) of Regulation (EU) 2024/1689; every policy has a version and a hash, and the hash goes into every record it decides. Scores from statistical verifiers drift slightly between machines, so each threshold carries a guard band, and a score inside it is `REVIEW` everywhere.

```python
record = verify(answer, sources, policy="eu_ai_act_high_risk_v1")
record.decision              # 'FAIL'
record.regulatory_mapping    # [{'article': 'Art. 15(1)', ...}, {'article': 'Art. 12(1)', ...}]
```

<br>

## Runtime

The runtime verifies an execution. It records each step of a run as an event in a hash-linked log, a model call, a retrieval, a tool request and its result, an action, a human approval, and an execution policy decides what the agent may do.

An execution policy is a short, ordered list of rules. Each rule matches a tool call or an action and carries an effect: `DENY` stops the step, `REVIEW` holds it for a human, `ALLOW` lets it proceed. The first rule that matches decides; when none does, the default applies, so a conservative deployment denies anything it did not explicitly allow. The gate is pure rule matching, with the same `exact` guarantee as the numeric verifier.

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

After a run, GroundLens audits the whole log against the policy, rolls it up to a single verdict, and flags any action that ran against it: one the policy forbade, or one that needed a human approval that never came. The verdict and the breaches go into the signed record, so an auditor can replay a run and see whether the policy was honoured.

<br>

## Evidence records

Whether GroundLens checked one answer or a whole run, the result is the same artefact: a signed record, chained to the one before it, that anyone can verify offline.

```python
record.content_hash     # same input, policy and bundle → same hash, on any machine
record.verify()         # recompute every hash and the Ed25519 signature, offline
Record.verify_chain(Record.read_log("records.jsonl"))
```

Change one byte anywhere in a record and verification fails. Append records to a JSON Lines log and each one carries the hash of the previous one. `groundlens report` turns a log into a human-readable report with a one-page guide for auditors.

<br>

## Quick start

```bash
pip install groundlens
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

**Enable the lexical verifier** (optional, once).

```bash
groundlens bundle pull base      # ≈470 MB
```

It downloads the base bundle (the multilingual-e5-small encoder in f32, its tokenizer and a manifest of hashes) from this repository's releases into a per-user directory, checks it against a hash pinned in the engine, and refuses anything else. It is the only command in the package that opens a network connection. With the bundle installed, the lexical verifier runs and every record names the bundle by hash. In an isolated environment, copy the bundle directory by hand and point `GROUNDLENS_BUNDLE_DIR` at it.

**The command line.** Everything except the lexical verifier works with the base install alone.

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

GroundLens is deterministic where it can be, and reproducible where it cannot.

`exact` verifiers and the execution gate use no floating point: the same input gives the same result, bit for bit, on any machine. `reproducible` verifiers run a pinned model in f32 on a pure-Rust inference engine, and their scores stay within a declared tolerance across machines. Anything `non_deterministic`, such as an LLM judge, is recorded with its model, prompt hash and settings, and decides only if the policy allows it.

This is tested, not asserted: CI runs the invoice example, with and without the lexical channel, on Linux, macOS and Windows under a Turkish locale and a Pacific timezone, and compares the record hash with a committed value.

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
