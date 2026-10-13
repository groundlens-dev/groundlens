<!--
SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
SPDX-License-Identifier: Apache-2.0
-->

# Design: what changes next, and why

This page describes the next shape of GroundLens. It was written before the
work started, and every change in the migration was checked against it.

Steps 1 to 11 of the plan at the end are built and merged; they ship together
in the next release. Each section below says what was built and where the
result differs from the plan. What is still not built is listed in
[Not built yet](#not-built-yet).

## Why it changes

Over the last months we measured how verification behaves on real answers from
real retrieval systems: annual reports (FinQA, 10-K filings), contracts
(LegalBench) and an EU regulation published after the models were trained, in
four languages. Five findings drive the design.

1. **Models rarely invent words. They attach real facts to the wrong thing.**
   The costly error is a correct figure from the wrong year, row, company or
   clause, or a correct fact that answers a different question. A check that
   asks "are the words of the answer in the source?" passes those errors,
   because the words are there.
2. **What counts as an error is a policy decision.** On the same contract
   answers the error rate moved from 11 % to 43 % depending only on the written
   definition of an error.
3. **A strong LLM judge is the only general checker that works, and it works
   best when it is told what it needs to know.** Giving the judge the written
   policy raised its detection from 63 % to 88 % and from 74 % to 98 %. Giving
   it the scope of the request (which company the question is about, which
   document each passage comes from) raised it from 68 % to 84 %.
4. **Judges from different vendors fail on the same answers.** A second judge
   is not a second opinion. Independent evidence has to fail in a different
   way: exact arithmetic, scope and intent checks.
5. **The lexical, entailment and similarity channels did not add value** on
   these answers. They check presence, not binding, and they add a model
   download, weight and latency.

We also asked six integrators, from three model families and without access to
this repository, to write the code they would want to use. They converged on
the same API and the same defaults. The design below follows them.

## What changes

| | today | next |
|---|---|---|
| default install | engine plus an optional model bundle | engine only, a few megabytes, no model, no network |
| checks in the default path | numeric, rules, lexical, entailment, similarity | scope, exact arithmetic, intent, rules, the judge you connect |
| lexical, entailment, similarity | in the default policies | optional, behind an extra, deprecated for one release |
| the judge | planned | a verifier: your model, a versioned template, claim-level evidence |
| scope and provenance | a passage has an id and a locator | a request has a scope; a passage has document, version, entity, page, hash |
| decisions | PASS / REVIEW / FAIL | the same, plus a risk class and a declared meaning of PASS |
| the record | written by the caller | written before the call returns; no record, no PASS |
| measurement | `calibrate()` per verifier | `measure`: error rate under your policy, with an interval and a cost |

What does not change: the five separations (verifiers, claims, evidence,
policy, record), "evidence, never truth", the Rust core without network, the
Ed25519 hash-chained records, and offline verification with a public key.
Records written today stay verifiable.

## The public API

Five names cover the whole surface: `Passage`, `Scope`, `Policy`, `Verifier`
and `Result`.

```python
import groundlens as gl

verifier = gl.Verifier(
    policy="policies/credit_desk.yaml",       # what counts as an error, for you
    judge=gl.judges.openai_compatible(client), # optional: the model you already use
    signer=gl.signers.aws_kms(key_id),         # optional: a local key in development
    sink=gl.sinks.jsonl("records/"),           # optional: S3 Object Lock, Blob WORM, Postgres
)

result = verifier.check(
    question=question,
    answer=answer,
    passages=[
        gl.Passage(text, doc_id="10-K-2016#p114", entity="UPS",
                   version="2016", page=114, sha256=digest),
    ],
    scope=gl.Scope(entity="UPS"),
)

result.decision      # PASS / REVIEW / FAIL
result.reasons       # stable codes with answer spans, worst first
result.record_id     # already signed and stored when check() returns
```

Rules the API follows:

- One object built once at start-up, one call per answer. `check()` and
  `acheck()`.
- With no policy file, a default policy applies, so a first test needs no
  configuration.
- The judge is optional and never required to get a decision from the
  deterministic checks.
- Checks are declared once, in the policy. Python only implements custom
  checks, registered by id.
- `check()` returns only after the record is signed and stored, and raises if
  it cannot be stored. A two-step form exists for batch writers.
- Results are plain data: they serialise to JSON without help.

Built in steps 8 to 11, with differences. `Verifier`, `check()`, `seal()` and
`store()` exist as written. `check()` returns the signed, stored `Record`, whose
`decision`, `reasons` and `record_id` are as above; the reasons are sentences,
and `groundlens.observe.reason_code` turns each into a stable code. Passages
are `(id, text, provenance)` tuples and the scope is a plain mapping; there are
no `Passage` or `Scope` classes yet, and no `acheck()`.

## Scope and provenance

Scope says what the request is about: an entity, a contract and its version, a
customer, a document set. Provenance says where each passage comes from. The
policy names the scope keys that are required and what happens when they are
missing or do not match.

The scope check is `exact`. A passage that the answer uses and that belongs to
another scope is `FAIL` by default. A missing scope key is `REVIEW`. Both the
scope and the provenance of every passage are hashed into the record, so the
record proves where each figure came from.

Built in step 3, as written.

## The checks

**Exact arithmetic.** Figures in the answer are matched to figures in the
passages and recomputed with exact rational arithmetic, under the rounding
rule and locale written in the policy (`1.234,56 €`, `en miles de euros`,
`1,5 %`). No floating point, no solver. A figure that is neither found nor
derivable is reported, not guessed.

**Intent.** The answer gives the kind of quantity that was asked: a percentage
when a percentage was asked, an amount when an amount was asked. Deterministic.
Emits `REVIEW`, never `FAIL`, because it is a heuristic.

**Units.** A figure without the unit the question requires, or with a
different one, is `REVIEW`. It reads the question, like the intent check, and
ships with it.

**The judge.** GroundLens does not ship a model. You pass the client you
already use (AWS Bedrock, Azure OpenAI, or any OpenAI-compatible endpoint,
including vLLM or Ollama on your own servers). GroundLens fills a fixed,
versioned template with the policy, the scope and the provenance of every
passage, and asks for evidence per claim: `supported`, `unsupported`,
`contradicted` or `uncertain`, with the passages behind each label. The judge
never decides. By default it can only escalate to `REVIEW`; a timeout or an
error is `REVIEW`, never `PASS`. Instructions found inside a passage are data,
not orders, and adversarial tests check it. `groundlens judge show-template`
prints the exact prompt for a given input, and its hash is in the record.

**Custom checks.** A decorated function or a small class, with a declared
determinism class. Its version and the hash of its source go into the record.

Built in steps 5, 6, 7 and 10: exact arithmetic, single-digit figures, intent,
units and the judge, as written. Custom checks registered from Python are not
built yet; rule sets (`rules=`) remain the way to add checks without Rust.

## The policy

YAML, checked against the schema. Unknown keys are errors. A policy can
`extends` a shipped baseline and write only what differs. Decision rules are a
fixed vocabulary evaluated in order; there is no expression language.

```yaml
id: credit_desk
version: 3.0.0
extends: eu_ai_act_high_risk_v1
locale: es-ES
rounding: half_even

scope:
  required: [entity]
  missing_scope: REVIEW

risk_classes:
  default: routine
  mandatory_review: [recommendation]

pass_means: "may be shown to the analyst as an evidence summary"
```

`groundlens policy show --resolved` prints the policy with every default
filled in. The resolved policy, not the partial file, is what gets hashed into
the record.

A decision of the verifier is not a decision to publish. The policy says what
PASS means for the application, and a risk class can require human review even
when every check passes.

Two choices made while building it. A passage outside the scope stays a
decision rule (`groundlens.scope` in `decision.any_contradiction_from`), not a
second key under `scope`, so there is one place that says what fails. The
mapping to controls keeps the existing `regulatory_mapping` list (framework,
article, control, requirement, the decisions that trigger it) rather than a
new `controls` key; your own control ids go in `control`.

## Failure semantics

| situation | decision |
|---|---|
| a passage the answer uses is outside the scope | FAIL |
| a figure contradicts the passages under the rounding rule | FAIL |
| a required scope key is missing | REVIEW |
| a passage has no provenance | REVIEW |
| the judge times out, errors or is not configured but required | REVIEW |
| the judge labels a claim unsupported or contradicted | REVIEW (FAIL only if the policy says so) |
| a required check could not run | REVIEW |
| the record cannot be stored | error: no decision is returned |

The final decision is the worst outcome of all checks. Built in steps 8 and
9, as written.

## The record

The plan below was for a schema `groundlens.evidence-record/2`; as built, the
record stays `/1` (see the two notes after it). The plan: it adds the scope,
the provenance of every passage, the resolved policy hash, the judge model
returned by the provider, the template hash and the hash of the judge's raw
response, and the version and source hash of every custom check. By default it
stores hashes, never the text of the question, answer or passages. Text is an
explicit opt-in.

Readers of `/2` verify records written as `/1`. The record format is versioned
separately from the library, and its specification is part of the
documentation.

Signing goes through a small interface with adapters for AWS KMS, Azure Key
Vault and PKCS#11; a local key file is for development only. Storage goes
through a sink interface with adapters for JSONL files, S3 Object Lock, Azure
Blob with immutability and Postgres. Many processes may write many chains;
`groundlens record verify` accepts a set of chains.

Built in step 9, with two choices. The key services sign with ECDSA on P-256,
not Ed25519, so the record envelope gained an optional `signature_algorithm`;
absent means Ed25519, so no existing record changes. The adapters take the
client the user already has (`boto3`, the Azure SDKs, a DB-API connection,
`python-pkcs11`), so the package keeps zero runtime dependencies. The move to
schema `/2` waited for the judge, which is what adds new content to the
record.

Built in step 10: the judge needed no new schema. It is a verifier like any
other, so its template id and hash, the prompt hash, the model the provider
returned and the hash of its raw reply are artefacts of its declaration in
the evidence graph, already covered by the content hash. The record stays
`groundlens.evidence-record/1`. The engine renders the prompt and reads the
reply; the caller's client is the only thing that talks to a model.

Not built: records still keep the passage text each piece of evidence points
to (`source_text`), so a record is not hashes only.

## Measurement

`groundlens measure` takes a batch of decisions and a small set of labels from
your own team (about 50, stratified by decision and risk class, labelled
without seeing the verdict) and reports:

- the rate of wrong answers that were passed, under your policy, with a
  confidence interval (prediction-powered inference);
- the same per risk class;
- the cost per decision: review minutes and the expected cost of an escaped
  error;
- the formula, the sample weights and the seed.

The report is signed. If the interval is wide, the report says so.
`groundlens replay` re-runs past traffic under a new policy, reusing the
stored judge evidence, and reports how many decisions would change.

Built in step 11. Replay needs the requests as sent, since a record keeps
hashes, not text; the judge's evidence is reused only when the prompt hash in
the old record matches the prompt the new policy would send. For that the
prompt carries what PASS means but not the policy's name or version.

## What this design does not do

- It does not bundle a model, and it does not require one.
- It does not run a server. The MCP server stays an option for agents.
- It does not use a solver in the core. Exact arithmetic covers the checks
  that worked.
- It does not claim compliance with any regulation. A policy maps decisions to
  your own controls; the mapping is yours.
- It does not promise to catch a correct figure taken from the wrong row
  without the judge. The deterministic checks cover scope, arithmetic, intent
  and units.

## How the migration is delivered

One pull request per step, in this order. Each step keeps the full test suite
green, keeps records written by the previous release verifiable, and updates
the documentation it touches in the same pull request.

1. **This design page and the roadmap.**
2. **Record compatibility fixtures.** Records written by the current release
   are committed and verified in CI, forever.
3. **Scope and provenance** in the input contract and the scope check. The
   record schema stays `/1`: scope and provenance are part of the input, so
   `input_hash` covers them.
4. **Model channels out of the default path.** Lexical, entailment and
   similarity run only when a request names a bundle, leave the shipped
   policies, and are deprecated with a warning. Their code leaves the default
   build in the next release, behind an opt-in feature and Python extra; one
   release of warning first, because removing it is not reversible for users.
5. **Exact arithmetic recompute** with a rounding rule. Figures the answer
   computed are recomputed from its own supported figures as exact fractions;
   years and formula constants stop counting as wrong figures; a unit or scale
   stated on one side only is support with a note. The rounding rule is a
   request option until step 7 moves it into the policy.
6. **Single-digit figures** with their own unit (`$2 million`) are read and
   checked.
7. **Intent check,** and the **units** check that reads the question: both
   compare the answer with what was asked.
8. **Policy schema:** `extends`, strict keys, risk classes, `pass_means`,
   `policy show --resolved`, failure semantics.
9. **Signer and sink interfaces;** `check()` stores before it returns.
10. **The judge verifier:** adapters, template, claim-level evidence,
   `judge show-template`, adversarial tests.
11. **Measurement and replay.**
12. **Regression suite on labelled real answers,** with recorded judge output,
    run in CI without network.

## Not built yet

- Step 12, the regression suite on labelled real answers with recorded judge
  output.
- `Passage` and `Scope` classes, and `acheck()`.
- Custom checks registered from Python, with their source hash in the record.
- Records that keep hashes only, with text as an opt-in.
- Removing the lexical, entailment and similarity channels from the default
  build. They are deprecated now and leave in the release after the next one.
