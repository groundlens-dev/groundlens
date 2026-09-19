<div align="center">

![GroundLens](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/groundlens_header.png)

## The verification and evidence layer for AI systems and agents.

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

[What it is](#what-groundlens-is) · [Built for AI systems and agents](#built-for-ai-systems-and-agents) · [How it works](#how-it-works) · [Engine](#engine) · [Verifiers](#verifiers) · [Policies](#policies) · [Evidence records](#every-check-leaves-a-record) · [Quick start](#quick-start) · [Determinism](#determinism) · [Examples](#examples) · [FAQ](https://github.com/groundlens-dev/groundlens/blob/main/FAQ.md) · [Roadmap](https://github.com/groundlens-dev/groundlens/blob/main/ROADMAP.md)

</div>

<br>

## What GroundLens is

AI systems, and increasingly agents, produce factual claims, recommendations and actions that an organisation is accountable for. When one of those outputs is later questioned, by a customer, a risk officer or an auditor, the organisation has to answer four things: was this specific output checked, with what, under which rules, and would the same check give the same result today. A score in a log cannot answer that. Your own application cannot vouch for itself.

GroundLens is the layer that answers it. You give it an AI output and, when they exist, the documents it was supposed to rest on. It runs independent checks on that output, applies the rules your organisation wrote, returns `PASS`, `REVIEW` or `FAIL`, and seals the whole check into a signed record that a third party can verify offline, without trusting you. It runs locally, needs no knowledge of how your system is built, and treats every check as evidence someone can inspect rather than a number they have to believe.

<br>

| Best for teams | Standout |
|---|---|
| Shipping AI answers and agents into regulated or high-stakes workflows who need proof, not a score, that each output was checked. | Several verification methods under one contract, with or without source documents (exact numeric and rule checks, lexical grounding, geometric indices, an optional LLM judge); policies in YAML that decide instead of hard-coded thresholds; signed, hash-chained records verifiable offline; no network, no runtime dependencies. |

<br>

## Built for AI systems and agents

GroundLens sits beside your AI system, not inside it. It observes what the system produces and the evidence around it, and turns that into a verifiable record. It never sees your weights, your prompts or your internal architecture, so independent verification is possible even in a bank or a sensitive deployment.

<div align="center">

![Where GroundLens sits](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/diagram_layer.png)

</div>

Today the shipped verifiers check answers and the claims inside them: numbers exactly, words by anchoring them to the sources, and your own symbolic rules. The same contract, an input that produces evidence, a policy that decides and a signed record that captures both, is designed to extend to the steps an agent takes: which tool it called, with what arguments, whether an action required human approval, what it read and wrote. That extension is the near-term direction, tracked in the [roadmap](https://github.com/groundlens-dev/groundlens/blob/main/ROADMAP.md). What ships in `pip install` today is described exactly below, with nothing marked as available that is not.

<br>

## How it works

<div align="center">

![How a verification works](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/diagram_pipeline.png)

</div>

<br>

| Verifier | Policy |
|---|---|
| A verifier produces evidence, not truth. Exact numeric checks, lexical grounding, semantic similarity, NLI, the geometric SGI and DGI indices, symbolic rules, your own verifiers and, if you allow it, an LLM judge: each one reports what it measured and how sure it is. None of them decides. | A policy interprets the evidence. A short YAML file you control says which verifiers are required, recommended, optional or forbidden, what thresholds apply, and how evidence becomes a decision. It can map each outcome to the governance or regulatory control it concerns, such as an article of the EU AI Act. |

The whole chain becomes a record. Input hashes, the verifiers and model hashes that ran, the evidence, the policy and its hash, the decision, the regulatory mapping, and the hash of the previous record, sealed with an Ed25519 signature. A log of records is an audit trail you can hand over as a file.

<br>

> GroundLens is AI system agnostic. It works on outputs and evidence, locally, with no network access, so independent verification is possible even in sensitive environments.

<br>

## Engine

GroundLens engine is a Rust library wrapped for Python, with no runtime dependencies and no network access of any kind. It contains the claim extractor, the exact **numeric** verifier (numbers, currencies, percentages, physical units, in several locales), the symbolic **rules** verifier, the **policy engine** with two bundled policies, and the signed **evidence records**.

The engine is a Rust workspace under `crates/`: contracts and hashing (`gl-core`), text normalisation (`gl-text`), numerals and units (`gl-numeric`), the verifiers, the policy engine, records, bundles, the model host (`gl-onnx`, on [tract](https://github.com/sonos/tract), no native library) and the one pipeline everything calls (`gl-engine`). The Python package is a thin binding over it; `glv` is the same engine as a binary. No engine crate depends on an HTTP or TLS library, and a CI job fails the build if one ever does.

```bash
cargo build --release                 # engine and glv
cd python && maturin build --release  # Python wheel
```

<br>

## Verifiers

| verifier | what it does | guarantee | in `pip install` |
|---|---|---|---|
| `groundlens.numeric` | numbers, currencies, percentages and physical units, compared exactly in base units: `1.2 km` equals `1200 m`, `212 °F` equals `100 °C`, `$37.35 billion` equals a table cell `37,350` under "in millions of dollars" | exact, bit-identical everywhere | yes |
| `groundlens.rules` | your own symbolic rules (an APR must be a percentage, a date must fall inside the contract term) | exact | yes |
| `groundlens.lexical` | whether each word of the answer is anchored in the sources, by contextual token similarity on a frozen multilingual encoder, reported as the weakest anchor rather than an average | reproducible: pinned model hash, scores within 1e-6 across machines | with the base bundle |
| NLI, semantic, SGI, DGI, LLM judge | entailment, meaning, geometric grounding and model-based judgement | optional verifiers, see the [roadmap](https://github.com/groundlens-dev/groundlens/blob/main/ROADMAP.md) | later releases |

Locales matter for numbers: `1.234` is one thousand in Spanish and one and a bit in English. GroundLens reads `en`, `es`, `ca`, `de`, `fr`, `it`, `pt`, `nl` and Swiss formats, knows short and long scale words, and keeps every legitimate reading of an ambiguous numeral instead of guessing. The base bundle's encoder covers about a hundred languages.

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

```python
record.content_hash     # same input, policy and bundle → same hash, on any machine
record.verify()         # recompute every hash and the Ed25519 signature, offline
Record.verify_chain(Record.read_log("records.jsonl"))
```

Change one byte anywhere in a record and verification fails. Append records to a JSON Lines log and each one carries the hash of the previous one. `groundlens report` turns a log into a human-readable report with a one-page guide for auditors.

<br>

## Quick start

`pip install` installs the GroundLens engine.

```bash
pip install groundlens     # installs the GroundLens engine
```

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

---

`groundlens bundle pull base` is a separate, explicit step.

```bash
groundlens bundle pull base      # optional: enables the lexical verifier (≈470 MB, once)
```

It downloads the **base bundle** (about 470 MB: the multilingual-e5-small encoder in f32, its tokenizer and a manifest of hashes) from this repository's releases into a per-user directory, checks it against a hash pinned in the engine, and refuses anything else. It is the only command in the package that opens a network connection. With the bundle installed, the **lexical** verifier runs and every record names the bundle by hash. In an isolated environment, copy the bundle directory by hand and point `GROUNDLENS_BUNDLE_DIR` at it.

---

The `groundlens` command line. Everything in this README except the lexical verifier works with the base install alone. Nothing leaves your machine.

```bash
groundlens verify --answer answer.txt --question question.txt \
  --source "invoice.pdf#p1=invoice.txt" --policy eu_ai_act_high_risk_v1 --log records.jsonl
groundlens record verify records.jsonl        # every hash, every link, every signature
groundlens report records.jsonl --out report  # report.md, report.json, README-auditor.md
groundlens policy lint policies/eu_ai_act_high_risk_v1.yaml
groundlens bundle status                      # is the base bundle installed, where, which hash
```

Exit codes: `0` PASS, `1` FAIL, `2` error, `3` REVIEW. The Rust binary `glv` exposes the same commands.

<br>

## Determinism

Same input, same answer, on any machine.

Each verifier declares what it guarantees. `exact` verifiers use no floating point at all. `reproducible` verifiers run a pinned model, in f32, on a pure-Rust inference engine, and their scores stay within a declared tolerance. Anything `non_deterministic`, such as an LLM judge, is recorded with its model, prompt hash and settings, and only decides if the policy says so.

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

<br>

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

<div align="center">

[groundlens.dev](https://groundlens.dev) · Javier Marín, 2026 (javier@groundlens.dev)

</div>
