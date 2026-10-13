<!--
SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
SPDX-License-Identifier: Apache-2.0
-->

# Architecture

This document describes how GroundLens is built: the idea it is organised
around, the layers of the pipeline, the core data contracts, the crate-by-crate
layout of the Rust workspace, and how the Python package and the command line
sit on top of it. It is the reference for anyone extending the engine, auditing
it, or embedding it in their own system.

## The idea in one line

GroundLens keeps five things separate that most tools blur together: the
**verifiers** that measure, the **evidence** they produce, the **policy** that
decides, the **regulatory mapping** a decision is tied to, and the **record**
that seals all of it. A verifier never decides; a policy never measures. That
separation is what makes a decision auditable: you can point at the exact
verifier that produced a signal, the exact policy that interpreted it, and the
exact rule that turned it into `PASS` / `REVIEW` / `FAIL` or `ALLOW` / `REVIEW`
/ `DENY`.

The unit of work is the **execution**: an ordered sequence of steps an AI
system takes. Verifying a single answer is the smallest execution, a run with
one claim, so one contract covers both a single answer and a whole agent run.

## The pipeline

```text
verification input  (question / answer / sources / metadata,  or  a run trace)
        │
        ▼
   claim / span layer          atomic claims with anchors  ·  or run events
        │
        ▼
   verifiers                    exact · symbolic · generative (your judge)
        │                       each: input → evidence, never input → truth
        ▼
   evidence graph               all evidence for all claims, conflicts kept
        │
        ▼
   policy engine                composition · scope · judge rules · risk class
        │
        ▼
   decision  +  regulatory mapping
        │
        ▼
   signed, append-only evidence record   (hash-chained; Ed25519 or a key service)
        │
        ▼
   sink                         stored before the decision is returned
```

The engine runs this once. Every surface, the Python package, the `glv` binary
and any future binding, calls the same pipeline, so there is exactly one
implementation of "verify under a policy and seal the record".

## The core contracts

These are the data types the whole system is built from. They live in
`gl-core` and change rarely, because everything else depends on their shape.

**Claim.** An atomic, checkable unit extracted from an answer, with a kind that
decides which verifiers apply: `numeric` (a quantity), `word` (a content word
with its span), `statement` (a sentence). A claim carries the span it came from,
so evidence can point back into the text.

**Verifier.** A function `input → evidence`. It reports what it measured and how
sure it is; it does not decide. Every verifier declares a **determinism class**
(`exact`, `reproducible`, `non_deterministic`) and, for a model-backed verifier,
the hash of the exact model graph it uses.

**Evidence.** The structured output of one verifier for one claim: the verifier
id and version, a result (`supported`, `contradicted`, `not_applicable`,
`error`, …), a score and confidence, the source span it backed or contradicted,
a model hash where relevant, and machine-readable notes. Evidence is kept, never
collapsed into a single number.

**Evidence graph.** All the evidence for a verification, indexed by claim. Two
verifiers can disagree about one claim; the graph keeps both, and the policy
decides what a conflict means.

**Policy.** A YAML document that turns evidence into a decision: which verifiers
are required, recommended, optional, fallback or forbidden; the minimum
determinism class it will decide on; thresholds with guard bands; the decision
rules (what fails, what reviews, what is tolerated); and a regulatory mapping.
It can also fix the locale and rounding rule, require scope keys, define risk
classes that always go to review, and say what `PASS` means. A policy may
`extends` a shipped one and write only what differs; unknown keys are errors.
A policy has a version and a hash, the hash of the resolved policy, and the
hash goes into every record it decides.

**Record.** The sealed result: input hashes, the engine version, the evidence
graph, the policy id and hash, the decision and its reasons, the regulatory
mapping, the previous record's hash, and a signature with the signer's public
key. A run adds its event log and gate verdict. The **content hash** covers
everything that is a function of the input and the policy, so the same check
gives the same content hash on any machine.

## The layers of a verifier

Verifiers are grouped by the guarantee they can give, which is what a policy
reasons about through the determinism class:

| layer | example | guarantee |
|---|---|---|
| exact | `groundlens.numeric`, `groundlens.scope`, the execution gate | deterministic, bit-identical everywhere |
| symbolic | `groundlens.intent`, `groundlens.rules` | deterministic, bit-identical everywhere |
| generative | `llm_judge.<adapter>`, your own model | non-deterministic, recorded: model, prompt hash, reply hash |
| model channels (deprecated) | `groundlens.lexical`, `groundlens.nli`, `semantic.cosine` | reproducible under a pinned model; run only when a request names a bundle |

The engine does not privilege any layer. A policy composes them: one deployment
runs numeric + scope + intent + rules and is fully deterministic; another adds
a judge and is not, but its record still names the model that answered and the
hashes of the prompt and the reply. The judge can only escalate: its agreement
resolves nothing.

## The workspace

GroundLens is a Rust workspace. Each crate has one job, and the dependency
direction runs from the contracts outward to the surfaces.

| crate | responsibility |
|---|---|
| `gl-core` | the contracts (claim, verifier, evidence, graph), canonical JSON, `content_hash`, `sha256`, error types |
| `gl-text` | Unicode normalisation, word and sentence segmentation, spans as byte offsets |
| `gl-numeric` | locale-aware parsing of numbers, currencies, percentages and physical units into base units |
| `gl-verifiers` | the built-in verifiers (`numeric`, `scope`, `intent`, `rules`; the deprecated `lexical`, `nli`, `semantic` behind features) and claim extraction |
| `gl-policy` | the policy schema, the linter, and `evaluate` (evidence graph → decision) |
| `gl-record` | signed, hash-chained records for answers and runs; external signatures (ECDSA P-256 from a key service); verification of a record, a chain and a set of chains; signed reports |
| `gl-bundle` | deprecated: the bundle format for the model channels |
| `gl-onnx` | deprecated: model hosting on `tract` (pure-Rust ONNX) for the model channels |
| `gl-runtime` | execution contracts: the run event log, the execution policy and the gate, the run audit |
| `gl-mcp` | the MCP adapter: JSON-RPC trace → run, recording hashes not content |
| `gl-engine` | the one pipeline, `verify()` and `verify_run()`, that every binding calls; the judge prompt and the reading of its reply |
| `gl-python` | the `pyo3` / `maturin` extension module (`groundlens._engine`) |
| `gl-cli` | the `glv` binary (and `groundlens`), the same engine on the command line |

`gl-core` depends on nothing in the workspace; `gl-engine` depends on the
verifiers, policy, record, bundle and runtime; the surfaces (`gl-python`,
`gl-cli`) depend only on `gl-engine`. No engine or runtime crate depends on an
HTTP or TLS library, and a CI job fails the build if one ever appears.

## The runtime and the gate

The runtime (`gl-runtime`) verifies an execution rather than a single answer. A
`VerificationRun` is an ordered, hash-chained event log: model calls,
retrievals, tool requests and their results, state reads and writes, human
approvals, actions, and policy decisions. It is pure data with no I/O; what it
stores of the world is hashes, not content.

The **gate** is an execution policy: an ordered list of rules, each matching a
tool (and optionally its server), an action, or a minimum risk class, and
carrying an effect. The first rule that matches decides; a default applies when
none does. `audit_run` rolls a finished run up to its strictest outcome and
flags **breaches**, an action that executed under a `DENY` rule or without a
required human approval. The gate is pure rule matching, `exact` like the
numeric verifier.

A run comes from what an agent already emits. `gl-mcp` ingests the JSON-RPC
messages of a Model Context Protocol session (`tools/call` and its result,
`sampling/createMessage`), correlates each request with its response, and
records hashes of the arguments and results. Recording a run needs no change to
how the agent is built.

## The judge

GroundLens ships no model and the engine never calls one. For a request with a
judge, the engine renders a fixed, versioned prompt (`groundlens.judge/1`) with
what PASS means, the scope, the question, the answer, and every passage with
its provenance, between markers the data can never contain. The caller's own
client sends it; the engine reads the reply into evidence per sentence. A reply
that is missing, late or not the JSON asked for is evidence too, and the policy
sends it to review.

## Determinism and the record

The exact and symbolic checks use integer and rational arithmetic, no floating
point, so they are bit-identical on every platform. The deprecated model
channels run under the `cpu-f32` profile on `tract`, with scores within `1e-6`
across x86-64 and arm64 and a guard band around every threshold.

The record ties all of this together. `content_hash` covers the input and the
resolved policy, so it is identical on any machine; the record id and timestamp are
deliberately left outside it. Records chain by carrying the previous record's
hash, which makes a log tamper-evident as a whole. Answer records and run
records share one signing envelope, so a single log can hold both.

## Surfaces

The Python package (`gl-python`, built with `maturin`) exposes the engine as
`groundlens`: `Verifier` (with `judges`, `signers` and `sinks`), `verify`,
`verify_run`, `measure`, and the `Record`, `RunRecord` and `Policy` types;
`proofread` stays for 3.x users. The wheel carries the compiled engine and has
no runtime dependencies; every adapter takes a client you already have.

The `glv` binary (`gl-cli`) is the same engine on the command line, with
`verify`, `record verify`, `policy lint`, `policy show`, `judge show-template`,
`keygen` and, for executions, `run verify` and `run check`. The Python command
line adds `report`, `measure` and `replay`. Both surfaces call `gl-engine` and
nothing else, so their behaviour cannot drift from each other.

For the user-facing reference, the API and CLI documentation and the concept
guides, see [groundlens.readthedocs.io](https://groundlens.readthedocs.io).
