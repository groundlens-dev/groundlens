# Claims and evidence

## Claims

Before any verifier runs, GroundLens breaks the answer into **claims**: the
atomic, checkable units a verifier can speak to. A claim has a kind, and the
kind decides which verifiers apply to it.

- **Numeric** claims are quantities found in the answer (amounts, percentages,
  measurements). The numeric verifier checks them.
- **Word** claims are content words, each with its span in the answer. The
  lexical verifier anchors them to the sources.
- **Statement** claims are sentences. The entailment verifier checks each one
  against its sources.

Claim extraction is deterministic and locale-aware. A claim that echoes the
question rather than asserting something new is noted, so it does not count
against the answer.

## Evidence

Each verifier returns structured **evidence** for the claims it can speak to.
Evidence carries, among other fields:

- `verifier_id` and the verifier's version, so the record names exactly what ran;
- `result` — `SUPPORTED`, `CONTRADICTED`, `NOT_APPLICABLE`, `ERROR`, and so on;
- `score` and, where relevant, a confidence;
- `source_text` / spans — which part of which source backed or contradicted the claim;
- `model_hash` — for ML verifiers, the sha256 of the exact model graph that produced the score;
- notes — machine-readable flags such as `exact_string_in_span`.

The point is that evidence is *kept*, not collapsed into a number. A record
holds everything every verifier said about every claim. See
{class}`groundlens.Evidence` for the fields.

## The evidence graph

All the evidence for a verification lives in an **evidence graph**: for each
claim, the evidence every admitted verifier produced, plus any verifier
failures. Two verifiers can disagree about the same claim; the graph keeps both,
and the policy decides what a conflict means (usually REVIEW).

## No verifier decides

A verifier can say `CONTRADICTED = 0.0` or `entailment = 0.91`, but none of them
knows what that means for your deployment. That translation — from evidence to
PASS / REVIEW / FAIL — is the [policy's](policies.md) job, and only the policy's.
