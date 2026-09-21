# Changelog

All notable changes to GroundLens. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/). One version per release,
identical in the git tag and on PyPI.

## [5.2.0] - 2026-09-21

### Added

- **Official MCP registry listing.** A `server.json` describing the server and
  its PyPI package, and an `mcp-name` marker in the README so the registry can
  verify PyPI ownership. GroundLens is now discoverable from the MCP registry
  and the directories that ingest it.

## [5.1.0] - 2026-09-21

### Added

- **MCP server** (`groundlens.mcp`, `pip install "groundlens[mcp]"`, command
  `groundlens-mcp`): verification as tools an agent or any Model Context Protocol
  client can call, over stdio. Three tools — `verify_answer`, `verify_run` and
  `verify_records` — each a thin layer over the engine. The MCP SDK is an
  optional dependency, so the base package keeps its zero dependencies. This is
  the counterpart to the 5.0 MCP adapter, which observes a session rather than
  serving one.

## [5.0.0] - 2026-09-21

The execution verification runtime. GroundLens now verifies an *execution*,
not only an answer, under the same contract: an input produces evidence, a
policy decides, a signed record captures both. An answer verification is a run
with one claim, so nothing in 4.x changes.

### Added

- **`gl-runtime`**, the execution contracts: a `VerificationRun` recorded as an
  ordered, hash-chained event log (`RunLog`) of model calls, retrievals, tool
  requests and results, state reads and writes, human approvals, actions and
  policy decisions. Pure data, no I/O, no network. What a run stores of the
  world is hashes, not content.
- **The gate** (`gl-runtime::gate`): an `ExecutionPolicy` of ordered rules that
  decides `ALLOW` / `REVIEW` / `DENY` for a tool call or an action
  (first match wins, with a default). `audit_run` rolls a finished run up to its
  strictest outcome and flags breaches: an action executed under a `DENY` rule,
  or one that needed a human approval that never came.
- **Run records** (`gl-record::run`): `seal_run` seals a run into a signed,
  hash-chained record with the same Ed25519, offline-verifiable guarantee as an
  answer record; `verify_run_record`, `verify_run_chain`,
  `verify_run_against_record`. The signing envelope is now shared by both record
  kinds with no change to 4.x answer records.
- **The MCP adapter** (`gl-mcp`): turns a real Model Context Protocol execution
  into a run. `McpRecorder` ingests JSON-RPC messages off a transport
  (`tools/call` and its result, `sampling/createMessage`), correlates request
  and response, and records hashes of arguments and results, never the content.
- **`gl-engine::run::verify_run`**: the one pipeline for a run
  (trace → event log → execution policy → signed record), next to `verify()`,
  called by every binding.
- **`glv run verify`** and **`glv run check`** on the command line, and
  **`groundlens.verify_run`** / **`groundlens.RunRecord`** in Python. Exit codes
  `0` / `3` / `1` on `ALLOW` / `REVIEW` / `DENY`.
- A runnable example under `examples/run` (an MCP trace, an execution policy and
  a README).
- **`groundlens.nli`**, the entailment verifier, wired into the engine: the
  answer is split into sentence-level statement claims, and when the loaded
  bundle carries an entailment model the verifier scores each claim against its
  sources. The shipped policies list it and tolerate unresolved statements, so
  decisions are unchanged; the model itself ships in a later bundle.
- **Documentation** on Read the Docs, built from the docstrings, with concept
  guides, a CLI reference and an `ARCHITECTURE.md` describing the workspace.

## [4.0.0] - 2026-09-10

GroundLens 4 is a new engine. The Python package name, the `proofread()`
API and the numeral semantics are kept; almost everything underneath is
new. Read the "Removed" section before upgrading.

### Added

- **GLV engine**, a Rust workspace (`crates/`) with one pipeline:
  claims → verifiers → evidence graph → policy → decision → signed record.
  The Python package (`groundlens._engine`) and the `glv` binary call the
  same code.
- **`verify()`**, the 4.x API: an answer, its sources, an optional
  question, a policy; returns a `Record`.
- **`groundlens.numeric`** verifier: exact comparison of numbers,
  currencies, percentages and physical units in base units, with locale
  profiles (`en`, `es`, `ca`, `de`, `fr`, `it`, `pt`, `nl`, `ch`, `und`),
  short and long scale words, header-declared scales ("in millions of
  dollars"), and two opt-in relaxations (`declared_precision`,
  `percent_as_fraction`), each noted in the receipt.
- **`groundlens.rules`** verifier: symbolic rules from YAML/JSON run as a
  verifier with exact determinism.
- **`groundlens.lexical`** verifier: the 3.x word-anchor channel
  (span-overlap alignment, overlapping windows, floor aggregate, receipts)
  on a pure-Rust ONNX host (tract) with a frozen multilingual encoder.
- **Policies** in YAML: required / recommended / optional / fallback /
  forbidden verifiers, minimum determinism class, thresholds with guard
  bands, decision rules, regulatory mapping. Bundled:
  `groundlens_default_v1` and `eu_ai_act_high_risk_v1` (Art. 15(1),
  Art. 14(4)(a), Art. 12(1) of Regulation (EU) 2024/1689).
  `groundlens policy lint` rejects thresholds on exact verifiers and guard
  bands narrower than twice the verifier tolerance.
- **Evidence records**: canonical JSON, content hash (input, policy,
  bundle, evidence, decision), record hash chained to the previous record,
  Ed25519 signature, JSON Lines log; `Record.verify()`,
  `Record.verify_chain()`, `groundlens record verify`.
- **Bundles**: a directory with `manifest.json`, hashed artefact by
  artefact, opened only if every hash matches; encoders declared in the
  manifest. The **`base` bundle** (multilingual-e5-small, f32, about
  470 MB) is published as a GitHub Release and installed with
  `groundlens bundle pull base`, which verifies the archive against a hash
  pinned in the engine. `bundle status`, `bundle build`, `bundle verify`.
  `GROUNDLENS_BUNDLE_DIR` for isolated environments.
- **Determinism classes** declared per verifier (`exact`, `reproducible`
  with tolerance, `non_deterministic`), scores quantised accordingly.
- **`groundlens report`**: `report.md`, `report.json`, `records.jsonl`
  and `README-auditor.md` from a log.
- **Command line** `groundlens` (and `glv`): `verify`, `report`,
  `record verify`, `policy lint`, `bundle {build,verify,status,pull}`,
  `keygen`. Exit codes `0` PASS, `1` FAIL, `2` error, `3` REVIEW. UTF-8
  output on every platform.
- **Cross-platform golden tests**: the invoice example, with and without
  the lexical channel, must produce the committed record hash on Linux,
  macOS and Windows under a Turkish locale and a Pacific timezone.
- **3.1 compatibility goldens**: numeral anchors (exact) and lexical
  anchors (within 1e-6) produced by groundlens 3.1 itself.
- Two Colab notebooks under `examples/notebooks/`.
- cargo-fuzz targets for the numeral, quantity, normalisation, policy and
  numeric-verifier parsers; a `fuzz` workflow.
- Supply chain: actions pinned by commit, CI pip tools pinned by hash,
  Dependabot, OpenSSF Scorecard workflow, `SECURITY.md` for 4.x.

### Changed

- **`proofread()`** keeps its signature and types, but the encoder now
  comes from a bundle (`bundle=` or the installed `base`) instead of a
  Python object. Without a bundle, only numerals are scored and the result
  says so in `warnings` (words carry the note `not_scored`).
- Function words are skipped per document locale (`es`, `ca`, `gl`, `de`,
  `fr`, `it`); 3.x skipped English function words only.
- Thin, figure, no-break and narrow no-break spaces survive
  normalisation as one canonical group separator (3.x lost U+00A0 to
  NFKC).
- Internally, spans are byte offsets into the normalised UTF-8 text;
  `proofread()` still returns character offsets, as in 3.x.
- The PyPI package has **zero runtime dependencies** and opens no network
  connection; the only network operation is the explicit `bundle pull`.
- Minimum Python is 3.10 (unchanged); wheels are `abi3`, one per platform.
- The repository README is the PyPI description.

### Removed

- `SentenceTransformerEncoder` and the `[encoder]` extra: encoders are
  bundle artefacts, pinned by hash, not `pip` dependencies.
  `proofread(encoder=...)` raises `TypeError` with guidance.
- The `[mcp]` extra and the MCP server of 3.x. An MCP server over the 4.x
  engine is on the roadmap.
- The numeral regex no longer treats `percent` / `por ciento` as part of
  the numeral span; the unit is still attached to the quantity.
- `python/README.md` (the repository README is used instead).

### Security

- No engine crate may depend on an HTTP or TLS library; a CI job fails the
  build if one appears.
- Bundle archives are hashed before unpacking; archives with links or
  paths escaping the target directory are refused.

## [3.1.0] and earlier

The 3.x Python implementation is kept at tag
[`v3.1.0`](https://github.com/groundlens-dev/groundlens/releases/tag/v3.1.0)
for reproducibility of published numbers. Its history is in the release
notes of each 3.x tag.

[5.2.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v5.2.0
[5.1.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v5.1.0
[5.0.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v5.0.0
[4.0.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v4.0.0
