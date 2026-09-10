# Roadmap


- [x]  4.0.0 · September 2026 · **Ships:** the GLV engine in Rust with Python bindings and the `groundlens` / `glv` command line; exact numeric verifier (locales, scale words,
currencies, percentages, physical units); symbolic rules verifier; lexical verifier on a pure-Rust ONNX host; policy engine with `groundlens_default_v1` and `eu_ai_act_high_risk_v1`; signed, hash-chained evidence records; the
`base` bundle (multilingual-e5-small, f32) with hash-pinned download; two Colab notebooks; cross-platform golden tests; 3.x `proofread()` kept and checked against golden files produced by 3.1.


- [x] 4.1 · October 2026 · Rust distribution and the first ML verifiers. Crates published on crates.io under `groundlens-*` names with a `groundlens` facade crate and `cargo install glv`; `nli.*` verifier (entailment on ONNX) and `semantic.*` verifier (sentence similarity), both on the same model host as the lexical channel; `base` bundle v2 carrying their models; policy thresholds and guard bands exercised by real statistical verifiers.

- [ ] 4.2 · November 2026 · geometry, calibration and your own verifiers. `sgi` and `dgi` verifiers (the geometric grounding indices from our papers) as optional verifiers; `groundlens calibrate` over a labelled log of records, producing a threshold per verifier with its false positive rate at the target recall; user-defined verifiers in Python (a small interface, declared determinism class, recorded like any built-in); adapters that run existing detectors (Vectara HHEM, LettuceDetect) as verifiers.

- [ ] 4.3 · December 2026 · the public benchmark. A public benchmark harness and report, "How existing AI
grounding methods behave at 95 % recall", reporting false positive rate at
95 % recall for every verifier and for common external methods, on public
datasets, reproducible from the repository; benchmark results referenced
by hash in calibration artefacts.

- [ ] 2027 Q1 · the evidence package. `groundlens report` as a complete evidence package (report,
auditor guide, records, policies and bundle hashes, verification
instructions) suitable for a procurement or conformity file; policy
templates per regulatory framework beyond the AI Act mapping shipped in
4.0; private-deployment guidance.


- [ ] HTTP and WASM bindings of the same engine; LLM-as-a-judge as a verifier
with recorded model, prompt hash and settings; bundles per language or
sector; an MCP server over the engine (the 3.x server is not in 4.0);
record attestation and transparency-log integration.

<br>

### What is not on this roadmap

A hosted console, multi-tenant SaaS, billing, review queues, telemetry.
They may come, but only after the engine, the evidence and the policies
have paying users. The rule for every item above is the same: does it make
GroundLens better verification infrastructure? If it only makes a nicer
dashboard, it waits.
