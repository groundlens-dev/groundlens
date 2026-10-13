# Roadmap

Shipped is marked done. **In main** means built and merged, and ships in the next release. Everything unmarked is not built yet.

- [x] **4.0.0** · September 2026 · shipped to PyPI. The GLV engine in Rust with Python bindings and the `groundlens` / `glv` command line; exact numeric verifier (locales, scale words, currencies, percentages, physical units); symbolic rules verifier; lexical verifier on a pure-Rust ONNX host; policy engine with `groundlens_default_v1` and `eu_ai_act_high_risk_v1`; signed, hash-chained evidence records; the `base` bundle (multilingual-e5-small, f32) with hash-pinned download; two Colab notebooks; cross-platform golden tests; 3.x `proofread()` kept and checked against golden files produced by 3.1.

- [x] **5.0.0** · September 2026 · shipped to PyPI. The execution verification runtime. GroundLens verifies an execution, not only an answer: a `VerificationRun` recorded as an ordered, hash-chained event log (model calls, retrievals, tool requests and results, actions, human approvals), in `gl-runtime`; an execution policy **gate** that decides `ALLOW` / `REVIEW` / `DENY` per tool call and action, with a whole-run audit that flags an action executed against the policy or without a required approval; signed **run records** with the same Ed25519, offline-verifiable guarantee as an answer record, in `gl-record`; the **MCP adapter** (`gl-mcp`) that turns a real Model Context Protocol trace into a run, recording hashes not content; and the end-to-end surface, `glv run verify` / `glv run check`, `groundlens.verify_run`, and a runnable example under `examples/run`. Additive: an answer verification is a run with one claim, so the 4.x pipeline is unchanged.

- [x] Also in the released package: the `calibrate()` operating-point tool. Deprecated in favour of `measure`; it leaves with the model channels.

- [x] **5.1.0** · September 2026 · shipped to PyPI. The **MCP server** (`groundlens.mcp`, `pip install "groundlens[mcp]"`, command `groundlens-mcp`): verification as tools an agent or any Model Context Protocol client can call, over stdio — `verify_answer`, `verify_run` and `verify_records`, each a thin layer over the engine. The MCP SDK is an optional extra, so the base package keeps its zero dependencies. This is the counterpart to the 5.0 MCP adapter, which observes a session rather than serving one.

- [x] **5.2.0** · September 2026 · shipped to PyPI. Listed on the **official MCP registry**: a `server.json` and an `mcp-name` marker in the README (PyPI ownership), so GroundLens is discoverable from the registry and the directories that ingest it.

- [x] **5.3.0** · September 2026 · shipped to PyPI. The first ML verifiers, live. The `base` bundle v2 ships the entailment model, so `groundlens.nli` runs after `bundle pull base`; a new `semantic.cosine` sentence-similarity verifier runs on the same encoder as the lexical channel; the shipped policies exercise real statistical verifiers. Also: the Windows CI matrix trimmed (abi3 wheels make it redundant), and releases sign their binaries and attach SLSA provenance as assets (OpenSSF Signed-Releases).

- [x] **In main.** **Scope and provenance.** A request carries its scope (entity, contract and version, customer, document set) and every passage carries its provenance (document, version, entity, page, hash). An exact scope check: a passage the answer uses from outside the scope is `FAIL`, a missing scope key is `REVIEW`. Scope and provenance are part of the input, so the record schema stays `groundlens.evidence-record/1` and `input_hash` covers them. Record compatibility fixtures in CI.

- [x] **In main.** **A lighter default path.** The lexical, entailment and similarity channels leave the default install and the shipped policies and move behind an extra, deprecated for one release. Our measurements on real answers showed that presence checks miss the costly errors. The default install becomes the engine alone, with no model and no network. In progress: the channels are now off unless a request names a bundle, the shipped policies no longer use them, and naming a bundle prints a deprecation warning; they leave the default build in the release after.

- [x] **In main.** **Exact arithmetic, units and intent.** Figures recomputed from the passages with exact rational arithmetic under the rounding rule and locale of the policy; a units check; an intent check (a percentage when a percentage was asked).

- [x] **In main.** **The policy as the single place of configuration.** `extends` from shipped baselines, unknown keys rejected, risk classes that can require human review, a declared meaning of `PASS`, `policy show --resolved`, and explicit failure semantics: a timeout, an error or a missing input is `REVIEW`, never `PASS`.

- [x] **In main.** **Signers and sinks.** Signing through AWS KMS, Azure Key Vault or PKCS#11; storage in JSONL, S3 Object Lock, Azure Blob with immutability or Postgres. `check()` returns only after the record is stored. The cloud and HSM adapters are tested against stand-ins with each SDK's call shapes, not yet against the live services.

- [x] **In main.** **The judge as a verifier.** The model you already use, through Bedrock, Azure OpenAI or any OpenAI-compatible endpoint, including your own servers. A versioned template filled with the policy, the scope and the provenance; evidence per claim; the judge can escalate to `REVIEW` and never decides on its own; `judge show-template`; adversarial tests against instructions hidden in passages.

- [x] **In main.** **Measurement and replay.** `measure`: the rate of wrong answers passed under your policy, with a confidence interval from a small labelled sample (prediction-powered inference), per risk class, with the cost per decision; signed. `replay`: how many decisions a policy change would flip on past traffic.

- [ ] **A regression suite on labelled real answers**, with recorded judge output, run in CI without network.

- [ ] Publish the crates on crates.io: this needs a package name for the binary, since `glv` on crates.io is an unrelated project.

- [ ] The runtime as a live path: an MCP proxy or gateway that gates tool calls in flight; more execution-event sources beyond MCP; HTTP and WASM bindings of the same engine.

The design behind these items, what was built and what is not built yet, is in [docs/design/next.md](docs/design/next.md).

<br>

### What is not on this roadmap

A hosted console, multi-tenant SaaS, billing, review queues, and any telemetry sent to us. They may come, but only after the engine, the evidence and the policies have paying users. The rule for every item above is the same: does it make GroundLens better verification infrastructure? If it only makes a nicer dashboard, it waits.
