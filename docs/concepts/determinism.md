# Determinism

GroundLens is deterministic where it can be and reproducible where it cannot.
The distinction is explicit: every verifier declares a **determinism class**,
and a policy can refuse to decide on evidence weaker than a class it names.

## The classes

| Class | Meaning | Example |
| --- | --- | --- |
| `exact` | No floating point. The same input gives bit-identical output, everywhere, always. | `groundlens.numeric`, `groundlens.rules` |
| `reproducible` | A pinned model in a fixed execution profile gives the same result within a declared tolerance across platforms. | `groundlens.lexical`, `groundlens.nli` |
| `non_deterministic` | Not guaranteed to repeat. Recorded in full, but a strict policy will not decide on it. | a future LLM-as-a-judge verifier |

## The reference execution profile

For reproducible verifiers the profile is `cpu-f32`: a float32 ONNX graph run by
[tract](https://github.com/sonos/tract) — pure Rust, single thread, no native
math library. Under that profile the same model file, identified by sha256,
gives scores within `1e-6` across x86-64 and arm64. That `1e-6` is the tolerance
the `reproducible` class declares. The profile is recorded in the bundle
manifest, so a GPU build can never masquerade as the reference profile.

## The guard band

A reproducible score can drift by up to its tolerance from one machine to
another. A threshold compared against a drifting score is exactly where a
classification could flip. The **guard band** closes that gap: a score within
`guard_band` of a threshold is REVIEW on every platform, so a platform
difference can never turn a PASS into a FAIL. A policy's guard band must be at
least twice the verifier's tolerance, and `policy lint` enforces it. See
[Policies](policies.md).

## What this buys the record

Because exact verifiers are bit-identical and reproducible verifiers are pinned
and guard-banded, the record's `content_hash` is the same for the same input,
policy and bundle on any machine, and a platform difference can never flip a
decision. That is what lets an auditor recompute a decision independently and
get the same answer.
