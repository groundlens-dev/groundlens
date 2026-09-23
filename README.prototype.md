<!-- SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info> -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# GroundLens

**Prove your AI ran under the controls you set, with evidence anyone can check.**

Sooner or later, someone will ask you to prove that an AI system operated under its controls.

Too often, when a system reaches production, the proof that it was under control lives in a folder: policies, spreadsheets, architecture diagrams, sample logs and test reports. That tells you what the system was supposed to do. It does not prove what happened when it ran.

GroundLens turns defined controls into executable verification over real AI execution, produces evidence, applies policy, and seals the result into a portable record that can be verified independently, offline.

> **CHECKED → METHOD → EVIDENCE → POLICY → DECISION → RECORD**

### Not a universal trust score

GroundLens does not reduce an AI system to a single 0 to 100 number. Numbers are useful when they measure something specific. GroundLens keeps each measurement tied to the verifier, evidence, policy and execution that produced it.

### Evidence without scope is not assurance

Every record states what was verified, what was not, and the boundary of the verification. A signed record of the wrong perimeter is not proof. This is the line an auditor can rely on, and the question you can ask of anyone else claiming to have "signed records": signed records of what, and how do you know you captured everything inside the boundary you claim.

## What it does

You define a control in plain terms. For example, "an answer must be supported by the retrieved sources", or "the agent may not move money without a human approval".

GroundLens does four things with it, every time the AI runs.

- Checks the execution against that control, using verifiers that produce evidence rather than a verdict.
- Applies your policy to that evidence and reaches a decision. Pass, review, or fail.
- Records what was checked, which verifier checked it, what evidence came out, which policy applied, and what was decided.
- Seals the record with a signature and a hash chain, so any change to it is detectable and anyone can confirm it independently.

## An example

A support agent may answer from the knowledge base but not invent policy. You set the control. GroundLens produces, for each answer, a record like this.

```
decision   REVIEW
control    ANSWER_MUST_BE_GROUNDED
claim      "Refunds are available for digital purchases"

numeric    NOT_APPLICABLE
grounding  UNSUPPORTED
           source: kb/refunds#p2
           evidence: "Refunds are issued within five business days"

policy     support_v1
           unsupported_claim -> REVIEW

scope      1/1 claims checked · 0 outside perimeter
record     signed · offline-verifiable · hash-chained
```

You can read it top to bottom. A verifier produced evidence, the policy turned that evidence into a decision, and the scope line states that one claim was checked and nothing was left outside the perimeter.

## How it works

One path, every time.

```
execution  ->  scope  ->  verify  ->  policy  ->  evidence  ->  signed record
```

A verifier produces evidence, never truth. GroundLens runs the verifiers, records their evidence, and lets policy determine how that evidence affects the decision. The decision and its evidence are sealed into a portable record.

The verification path is designed to run without network access. Deterministic checks produce stable results. Model based verifiers are reproducible only under their declared artifact and configuration constraints, and the record states which ones ran and with what settings.

Verifiers are pluggable. Exact numeric and rule checks are deterministic. Entailment and similarity checks add model based judgement. An external detector, or an LLM used as a judge, can be wrapped as one more verifier. GroundLens does not care which ones you choose. It runs them, records what they said, and makes the result checkable.

## What you can do with it

The same record answers four questions that teams are starting to face as AI moves into production.

**Make a rule executable.** A regulation or an internal standard says you must be able to trace what the system did. GroundLens turns that requirement into a concrete test, runs it, and keeps the evidence, instead of leaving you with a document and a promise.

**Follow an action across systems.** When a business task is carried out by several agents crossing several platforms, no single platform can reconstruct the whole chain. A portable, vendor neutral record can.

**Re-check only what changed.** A model, a prompt, a tool, or a permission changes. GroundLens re-runs the controls that the change affects and produces fresh evidence, so a small change does not force a full re-review.

**Reconstruct a past decision.** Months later someone asks why the system did what it did. A signed record of what was checked at the time answers the question that a live dashboard cannot.

## Why it is different

**Evidence, not a rating.** You get a record you can review, investigate and present, not a score whose meaning nobody can pin down.

**It states its own limits.** The evidence is explicit about what was checked and what was outside scope. An honest perimeter is what makes the rest worth anything.

**Someone else can check it.** A record produced here is designed to be verified three ways: by the command line, by the Python library, and by a from-scratch verifier that shares no code with GroundLens. Portable evidence, not "trust our platform".

**Cheap enough to run on everything.** The deterministic core is designed to run continuously and locally, with no per-check model bill, so you can verify every run instead of sampling a few.

## Quick start

```bash
pip install groundlens
```

```python
from groundlens import verify

record = verify(
    "Refunds are processed in 3 days.",
    evidence=[("kb/refunds#p2", "Refunds are issued within five business days.")],
    policy="eu_ai_act_high_risk_v1",
)

print(record.decision)     # FAIL  (3 days contradicts five business days)
print(record.reasons)      # what a reviewer should read first
record.verify()            # recompute hashes and signature, offline
```

From the command line.

```bash
groundlens verify --answer "…" --source kb/refunds#p2:"…"
groundlens record verify records.jsonl     # re-check a sealed log
```

## Who it is for

Engineers integrate it. Risk and compliance teams rely on it. Auditors verify it. Each of them can meet the record on their own terms, which is why the same artifact works for all three.

## Verify it yourself

GroundLens ships a suite that checks the tool against its own promises, so you do not have to take them on faith.

```bash
python suite/conformance.py        # does it do what it says
python suite/performance.py        # latency, throughput, record size
python suite/interoperability.py   # one record, three independent verifiers
```

The performance numbers are whatever they measure on your machine. The suite prints the machine it ran on, so a number always comes with the conditions that produced it.

## Standards it builds on

The evidence model reuses established primitives rather than inventing its own. SHA-256 for hashing, Ed25519 signatures, canonical JSON, and append-only hash chaining in the style of transparency logs, together with the tamper-evident, independently verifiable pattern of content provenance and verifiable credentials.

GroundLens can encode controls derived from applicable regulatory and internal requirements, with the mapping recorded alongside the verification evidence. It does not claim legal conformity on your behalf. See `suite/STANDARDS.md`.

## License

Apache 2.0.
