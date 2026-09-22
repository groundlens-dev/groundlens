# Roadmap

Shipped is marked done. Everything unmarked is not built yet.

- [x] **4.0.0** · September 2026 · shipped to PyPI. The GLV engine in Rust with Python bindings and the `groundlens` / `glv` command line; exact numeric verifier (locales, scale words, currencies, percentages, physical units); symbolic rules verifier; lexical verifier on a pure-Rust ONNX host; policy engine with `groundlens_default_v1` and `eu_ai_act_high_risk_v1`; signed, hash-chained evidence records; the `base` bundle (multilingual-e5-small, f32) with hash-pinned download; two Colab notebooks; cross-platform golden tests; 3.x `proofread()` kept and checked against golden files produced by 3.1.

- [x] **5.0.0** · September 2026 · shipped to PyPI. The execution verification runtime. GroundLens verifies an execution, not only an answer: a `VerificationRun` recorded as an ordered, hash-chained event log (model calls, retrievals, tool requests and results, actions, human approvals), in `gl-runtime`; an execution policy **gate** that decides `ALLOW` / `REVIEW` / `DENY` per tool call and action, with a whole-run audit that flags an action executed against the policy or without a required approval; signed **run records** with the same Ed25519, offline-verifiable guarantee as an answer record, in `gl-record`; the **MCP adapter** (`gl-mcp`) that turns a real Model Context Protocol trace into a run, recording hashes not content; and the end-to-end surface, `glv run verify` / `glv run check`, `groundlens.verify_run`, and a runnable example under `examples/run`. Additive: an answer verification is a run with one claim, so the 4.x pipeline is unchanged.

- [x] Also in the released package: the `calibrate()` operating-point tool, which turns a labelled log into a per-verifier threshold and always returns its measured false-positive rate at 95 % recall alongside it.

- [x] **5.1.0** · September 2026 · shipped to PyPI. The **MCP server** (`groundlens.mcp`, `pip install "groundlens[mcp]"`, command `groundlens-mcp`): verification as tools an agent or any Model Context Protocol client can call, over stdio — `verify_answer`, `verify_run` and `verify_records`, each a thin layer over the engine. The MCP SDK is an optional extra, so the base package keeps its zero dependencies. This is the counterpart to the 5.0 MCP adapter, which observes a session rather than serving one.

- [x] **5.2.0** · September 2026 · shipped to PyPI. Listed on the **official MCP registry**: a `server.json` and an `mcp-name` marker in the README (PyPI ownership), so GroundLens is discoverable from the registry and the directories that ingest it.

- [x] **5.3.0** · September 2026 · shipped to PyPI. The first ML verifiers, live. The `base` bundle v2 ships the entailment model, so `groundlens.nli` runs after `bundle pull base`; a new `semantic.cosine` sentence-similarity verifier runs on the same encoder as the lexical channel; the shipped policies exercise real statistical verifiers. Also: the Windows CI matrix trimmed (abi3 wheels make it redundant), and releases sign their binaries and attach SLSA provenance as assets (OpenSSF Signed-Releases).

- [ ] Publish the crates on crates.io: this needs a package name for the binary, since `glv` on crates.io is an unrelated project.

- [ ] **5.4** · geometry and your own verifiers. `sgi` and `dgi` verifiers (the geometric grounding indices from our papers) as optional verifiers; user-defined verifiers in Python (a small interface, a declared determinism class, recorded like any built-in); adapters that run existing detectors (Vectara HHEM, LettuceDetect) as verifiers.

- [ ] **5.5** · the public benchmark. A public benchmark harness and report, "How existing AI grounding methods behave at 95 % recall", reporting false-positive rate at 95 % recall for every verifier and for common external methods, on public datasets, reproducible from the repository; benchmark results referenced by hash in calibration artefacts.

- [ ] **5.6** · the evidence package. `groundlens report` as a complete evidence package (report, auditor guide, records, policies and bundle hashes, verification instructions) suitable for a procurement or conformity file; policy templates per regulatory framework beyond the AI Act mapping shipped in 4.0; private-deployment guidance.

- [ ] The runtime as a live path, not only a recorder: an MCP proxy or gateway that gates tool calls and actions in flight (the 5.0 adapter records and audits a trace; this stands in the execution path and enforces); signer identity and trust for run records; more execution-event sources beyond MCP.

- [ ] HTTP and WASM bindings of the same engine; LLM-as-a-judge as a verifier with recorded model, prompt hash and settings; bundles per language or sector; record attestation and transparency-log integration.

<br>

### What is not on this roadmap

A hosted console, multi-tenant SaaS, billing, review queues, telemetry. They may come, but only after the engine, the evidence and the policies have paying users. The rule for every item above is the same: does it make GroundLens better verification infrastructure? If it only makes a nicer dashboard, it waits.
