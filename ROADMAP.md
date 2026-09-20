# Roadmap

Shipped is marked done. Everything unmarked is not built yet.

- [x] **4.0.0** · September 2026 · shipped to PyPI. The GLV engine in Rust with Python bindings and the `groundlens` / `glv` command line; exact numeric verifier (locales, scale words, currencies, percentages, physical units); symbolic rules verifier; lexical verifier on a pure-Rust ONNX host; policy engine with `groundlens_default_v1` and `eu_ai_act_high_risk_v1`; signed, hash-chained evidence records; the `base` bundle (multilingual-e5-small, f32) with hash-pinned download; two Colab notebooks; cross-platform golden tests; 3.x `proofread()` kept and checked against golden files produced by 3.1.

- [x] **5.0** · the execution verification runtime, in `main`. GroundLens verifies an execution, not only an answer: a `VerificationRun` recorded as an ordered, hash-chained event log (model calls, retrievals, tool requests and results, actions, human approvals), in `gl-runtime`; an execution policy **gate** that decides `ALLOW` / `REVIEW` / `DENY` per tool call and action, with a whole-run audit that flags an action executed against the policy or without a required approval; signed **run records** with the same Ed25519, offline-verifiable guarantee as an answer record, in `gl-record`; the **MCP adapter** (`gl-mcp`) that turns a real Model Context Protocol trace into a run, recording hashes not content; and the end-to-end surface, `glv run verify` / `glv run check`, `groundlens.verify_run`, and a runnable example under `examples/run`. Additive: an answer verification is a run with one claim, so the 4.x pipeline is unchanged.

- [x] Also in the released package: the `calibrate()` operating-point tool, which turns a labelled log into a per-verifier threshold and always returns its measured false-positive rate at 95 % recall alongside it.

- [ ] **5.1** · Rust distribution and the first ML verifiers. Ship the entailment model in a `base` bundle v2 (`groundlens.nli` is wired into the pipeline and runs whenever a bundle carries the model) and add a `semantic` sentence-similarity verifier, both on the model host the lexical channel already uses; policy thresholds and guard bands exercised by real statistical verifiers; publish the crates on crates.io (this needs a package name for the binary, since `glv` on crates.io is an unrelated project).

- [ ] **5.2** · geometry and your own verifiers. `sgi` and `dgi` verifiers (the geometric grounding indices from our papers) as optional verifiers; user-defined verifiers in Python (a small interface, a declared determinism class, recorded like any built-in); adapters that run existing detectors (Vectara HHEM, LettuceDetect) as verifiers.

- [ ] **5.3** · the public benchmark. A public benchmark harness and report, "How existing AI grounding methods behave at 95 % recall", reporting false-positive rate at 95 % recall for every verifier and for common external methods, on public datasets, reproducible from the repository; benchmark results referenced by hash in calibration artefacts.

- [ ] **5.4** · the evidence package. `groundlens report` as a complete evidence package (report, auditor guide, records, policies and bundle hashes, verification instructions) suitable for a procurement or conformity file; policy templates per regulatory framework beyond the AI Act mapping shipped in 4.0; private-deployment guidance.

- [ ] The runtime as a live path, not only a recorder: an MCP proxy or gateway that gates tool calls and actions in flight (the 5.0 adapter records and audits a trace; this stands in the execution path and enforces); signer identity and trust for run records; more execution-event sources beyond MCP.

- [ ] HTTP and WASM bindings of the same engine; LLM-as-a-judge as a verifier with recorded model, prompt hash and settings; bundles per language or sector; an MCP **server** that exposes verification as a tool an agent can call (distinct from the 5.0 adapter, which observes MCP rather than serving it; the 3.x server is not in 4.x); record attestation and transparency-log integration.

<br>

### What is not on this roadmap

A hosted console, multi-tenant SaaS, billing, review queues, telemetry. They may come, but only after the engine, the evidence and the policies have paying users. The rule for every item above is the same: does it make GroundLens better verification infrastructure? If it only makes a nicer dashboard, it waits.
