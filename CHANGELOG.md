# Changelog

All notable changes to GroundLens. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/). One version per release,
identical in the git tag and on PyPI.

## [Unreleased]

### Added

- **Scope and provenance.** A request can state its scope (`scope={"entity":
  "AAPL"}`, `--scope entity=AAPL`) and every source its provenance (a third
  tuple element or a `provenance` key in Python, `--provenance id:key=value`
  on the command line). Both are hashed into the record's `input_hash`.
- **`groundlens.scope`**, an exact verifier that runs when a scope is stated.
  A figure found only in passages outside the scope is `contradicted` (note
  `out_of_scope_source`); a figure found only in passages that do not state
  their provenance is `unsupported` (note `provenance_missing`). This is the
  error measured most often on unfiltered retrieval: a real figure from
  another company's report.
- **Recomputed figures.** `groundlens.numeric` 1.1.0 checks a figure that no
  source contains against the other figures of the same answer that the
  sources support: their sum, difference, ratio and percentage change,
  computed as exact fractions and compared at the precision the answer wrote.
  A match is `supported` with the note `derived` and the formula in the
  rationale; wrong arithmetic stays a contradiction. Only the answer's own
  supported figures are operands, never pairs of source figures.
- **A rounding rule** for recomputed figures: `half_up` (default),
  `half_even` or `within_last_digit` (rounded or truncated). `rounding=` and
  `derive=` in Python, `--rounding` and `--no-derive` on both command lines.
- **`groundlens.intent`**, a deterministic check that runs when a request has
  a question. It reads what the question asks for (a percentage, a count, an
  amount, a named unit such as euros) and the answer's last figure that is not
  a year. A figure of another kind is `unsupported` with the note
  `intent_mismatch`; another unit is `unit_mismatch`; no unit where one was
  asked is `unit_missing`. On 192 labelled answers over annual reports it
  flagged 10, of which 8 were wrong.
- **`decision.unsupported_from`** in policies: an `unsupported` from a listed
  verifier sends the claim to review. Left out of the policy hash when empty,
  so existing policies keep their hash.
- **`extends`** in policies. A policy can be written on top of
  `groundlens_default_v1` or `eu_ai_act_high_risk_v1` and say only what
  differs: maps merge key by key, lists and single values replace. It must set
  its own `id` and `version`. The hash in every record is the hash of the
  resolved policy.
- **`groundlens policy show POLICY --resolved`** (and `glv policy show`)
  prints a policy with `extends` merged in and every default written out,
  headed by its hash. `policy lint` and `--policy` also accept the id of a
  shipped policy.
- **`scope.required`** in policies: a request without a required scope key
  goes to `missing_scope` (`REVIEW` by default, `FAIL` allowed, never
  `PASS`).
- **`risk_classes`** in policies, and `risk_class=` / `--risk-class` on a
  request. A class under `mandatory_review` goes to review even when every
  check passes; a class the policy does not list is an error. The class is
  written into the decision.
- **`pass_means`**: one sentence on what `PASS` means for the application. It
  travels in the policy and in the decision of every record.
- **`locale` and `rounding`** in policies. When a policy sets them they win
  over the request.
- The Python command line accepts `--scope`, `--provenance` and
  `--risk-class`, like `glv`.
- **`groundlens.Verifier`**: a policy, a signer and a sink set once, then
  `check()` per answer. `check()` returns only after the record is signed and
  stored; if it cannot be stored it raises `StoreError` and returns no
  decision. `seal()` and `store()` are the two-step form for batch writers.
- **Signers** (`groundlens.signers`): `local_key` (Ed25519, development),
  `aws_kms`, `azure_key_vault` and `pkcs11`. With a key service the key never
  leaves it: the engine builds the record, the service signs its
  `record_hash`, and the engine checks the signature before it returns the
  record. Key services sign with ECDSA on P-256; such a record carries
  `signature_algorithm: ecdsa-p256-sha256`. A record without the field is
  Ed25519, so every existing record keeps its bytes and verifies as before.
- **Sinks** (`groundlens.sinks`): `jsonl` (fsynced), `s3_object_lock`,
  `azure_blob` and `postgres`. Each keeps one chain and writes each position
  once; a writer that loses a race is told, and `check()` seals again on the
  new head. You pass the client you already use; the package keeps zero
  runtime dependencies.
- **`record verify` takes several chains**: several files, or a directory
  with one `.jsonl` per chain. Every chain must verify on its own, and no
  record may be in two chains. `Record.verify_chains()` in Python.
- **The judge** (`groundlens.judges`): the model you already use, through
  `openai_compatible` (OpenAI, vLLM, Ollama, any compatible gateway),
  `azure_openai` or `bedrock`, passed as `Verifier(judge=...)`. GroundLens
  ships no model and the engine never calls one: it renders a fixed prompt
  (`groundlens.judge/1`) with what PASS means, the scope and the provenance
  of every passage (not the policy's name, so a reply stays reusable on
  replay), the caller's client answers, and the engine reads the reply
  into evidence per sentence under `llm_judge.<adapter>`. The record keeps the
  template id and hash, the prompt hash, the model the provider says answered
  and the hash of the raw reply, not the reply.
- **`judge` in policies**: `required`, and what `contradicted` and
  `unsupported` (which covers `uncertain`) lead to, `REVIEW` by default. The
  judge's `supported` resolves nothing, so a judge cannot pass an answer the
  exact checks fail. A timeout, an error or a reply that is not the JSON asked
  for is `REVIEW`.
- The MCP server's `verify_answer` accepts `scope`, `risk_class` and a
  `provenance` per source, and returns the request-level `reasons`.
- **`groundlens measure`**: the share of wrong answers among those that
  passed, with a 95 % interval, per risk class, and the cost per decision
  (review minutes, expected cost of a wrong answer that got through), from a
  sample your team labels without seeing the verdict. `--sample N` draws the
  sample per decision and risk class. Agresti-Coull within each stratum, or
  prediction-powered when every record has a prediction. The report is
  signed (`groundlens.measurement/1`) and says how it was computed.
- **`groundlens replay`**: past traffic checked again under another policy,
  with the count and list of decisions that would change. The judge's stored
  evidence is reused when it answered the same prompt. Signed
  (`groundlens.replay/1`).
- `gl_record::SignedDocument`, `sign_document`, `verify_document` for signed
  reports; `VerifyRequest::judge_evidence` to replay a judge's stored evidence.
- **`groundlens judge show-template`** (and `glv judge show-template`) prints
  the exact prompt for an input, with its hash. `Verifier.judge_prompt()` in
  Python.
- In Rust, `gl_record::prepare_unsigned` and `gl_record::attach_signature`,
  and `gl_engine::verify_unsigned`.
- Request-level reasons in the decision (`outcome.reasons`): a missing scope
  key, a verifier that could not run, a risk class that requires review.
  Omitted when empty, like the new `risk_class` and `pass_means` fields, so
  records that use none of them keep their hash.
- **Observers and connectors.** `Verifier(observers=[...])` tells each
  observer about a check after its record is stored: the record, and how long
  each step took (`groundlens.observe.CheckEvent`). Observers never change a
  decision; an observer that raises is logged and ignored.
  - `gl.integrations.otel()`: OpenTelemetry spans (`groundlens.check`, the
    judge with `gen_ai.*` attributes, one span per verifier, the signer, the
    store) under the caller's trace, and the metrics `groundlens.decisions`,
    `groundlens.reasons` and `groundlens.check.duration`.
    `pip install "groundlens[otel]"`.
  - `gl.integrations.langfuse(client)`: the check inside the Langfuse trace of
    the answer, as a guardrail observation with the judge as a generation,
    and the decision as the categorical score `groundlens.decision`.
    `pip install "groundlens[langfuse]"`.
  - `gl.integrations.grafana_dashboard()`: a Grafana dashboard for those
    metrics and spans, to import.
  - `groundlens.observe.reason_code`: a short code for each reason
    (`groundlens.numeric.contradicted`, `mandatory_review`), fit for a metric
    label.
  - `examples/observability/`: a credit assistant watched in Grafana or
    Langfuse.
- `gl_engine::verify_timed` and `verify_unsigned_timed` return how long each
  verifier took, outside the record.

### Changed

- **Shipped policies 1.1.0.** `groundlens_default_v1` and
  `eu_ai_act_high_risk_v1` list `groundlens.scope` as recommended, fail on its
  contradictions and review its unsupported claims. Their hashes change, and
  so do the golden content hashes of the invoice example; the evidence and the
  input hash of a request without a scope are unchanged. Records written under
  1.0.0 keep verifying.

- **No model runs unless a request names a bundle.** An installed `base`
  bundle is no longer used by default: the lexical, entailment and similarity
  channels run only with `--bundle base` or `bundle="base"`. A request without
  a bundle records `sha256:unbundled` whatever is installed on the machine, so
  the same request gives the same record everywhere. A policy that requires
  `groundlens.lexical` without a bundle named now fails with a message that
  says to pass one. `proofread()`, the word-level facade kept from 3.x, still
  uses the installed `base` bundle when none is named.
- **Shipped policies 1.3.0.** They recommend
  `groundlens.intent` and send its `unsupported` to review, never to fail.
  Records of requests with a question name the new verifier, so the golden
  content hashes of the invoice example change; its decision does not.
- **Shipped policies 1.2.0.** `groundlens_default_v1` and
  `eu_ai_act_high_risk_v1` no longer list the model channels and drop their
  thresholds. Decisions on requests without a bundle are unchanged; the
  policy version and hash in the record change, and so do the golden content
  hashes of the invoice example.

- **Fewer false failures on numbers.** A bare year missing from the sources is
  `unsupported` (note `year_not_in_sources`), not a contradiction. The `100`
  of `× 100` and the divisor of an average are no longer claims. The same
  written number with a unit or scale on one side only (`$5,312 million`
  against a table cell `5312`) is `supported` with the note
  `unit_or_scale_on_one_side`, from three significant digits. On 192 labelled
  answers over annual reports, correct answers that failed went from 90 % to
  32 %; the wrong answers no longer flagged all had correct arithmetic on
  figures from the wrong row, year or company. Records name verifier version
  1.1.0, so the golden content hashes of the invoice example change; its
  evidence and decision do not. `proofread()` keeps its 3.x numeral
  semantics.

- **The Rust toolchain in CI is pinned** to `1.99.0` in the Rust, Python and
  release workflows, instead of following `stable`. A new Rust release can add
  clippy lints that break the build with no change to the code, as 1.99 did.
  The version is raised on purpose, in its own pull request, after checking
  `cargo clippy --workspace --all-targets -- -D warnings` with the new
  version. The MSRV job keeps checking `1.91`, and the fuzz job keeps
  `nightly`.
- **Unknown keys in a policy are errors.** Before, a misspelt key was ignored,
  so a typo could switch a rule off without anyone noticing. The shipped
  policies have no unknown keys and keep their hashes.
- **Nothing that went wrong can pass.** A verifier that could not run at all
  sends the request to review (unless the policy forbids that verifier), and
  a verifier error on a claim that needs a verdict sends the claim to review.
  Before, both were skipped. Claim kinds the policy tolerates without a verdict
  (`word`, `statement` in the shipped policies) are unchanged.
- **The shipped policies live in the `gl-policy` crate**
  (`crates/gl-policy/policies/`), so the engine, the command lines and
  `extends` read one source. The copies under `policies/` and in the Python
  package stay, and a test checks they are identical.

### Deprecated

- **`calibrate()`** raises a `DeprecationWarning` and leaves with the model
  channels it calibrates. To know how many wrong answers a policy lets through,
  use `groundlens measure`. Its guide and the bundles page move to a
  "Deprecated" section of the docs.

- **The model channels: `groundlens.lexical`, `groundlens.nli` and
  `semantic.cosine`,** and the `bundle` argument that feeds them. On real
  answers from annual reports, contracts and a regulation they did not add
  value: they check that words are present, not that a figure is bound to the
  right company, year or clause, and they add a model download, weight and
  latency. Naming a bundle prints a warning (`DeprecationWarning` in Python).
  They leave the default build in the next release.

### Removed

- `README.prototype.md`, a positioning draft nothing linked to.
- `suite/verifier_evaluation/`, the FPR-at-95-%-recall benchmark of the model
  channels against other detectors. What a deployment lets through is now
  measured under its own policy with `groundlens measure`.
- `scripts/workflows/`, `scripts/dependabot.yml` and `scripts/pin_actions.py`:
  an old copy of the CI workflows that had drifted from `.github/workflows`;
  running the script would have rolled the live CI back. Dependabot keeps the
  pinned actions up to date in `.github/` directly.
- Ten unused images under `docs/assets/`.

### Fixed

- **A decimal point no longer ends a sentence.** `$37.35 billion` was split
  into two sentence claims at the point. Only the meaning channels and the
  judge read sentences, so no decision changes, but the claim list, and with
  it the input hash, does: the golden content hashes of the invoice example
  (`crates/gl-cli/tests/golden/invoice.hash` and `invoice-lexical.hash`)
  change. The evidence and the decision of the example are the same, under
  claim ids shifted by the two fragments that are gone.

- **A single-digit figure with its own unit is checked.** `$2 million`, `5 %`
  and `7 days` were never read as figures, so they were never verified. A
  single digit now counts when a currency, a percent sign, a unit or a scale
  word is attached to it. Bare single digits stay out (list numbers, page
  numbers), and so do a digit glued to a word (`Q4`), an abbreviated scale
  without a currency (`3M` is a company, `$3M` is money) and a digit under a
  header scale alone. `proofread()` keeps its 3.x numerals.
- A needless borrow in the numeric verifier flagged by clippy in Rust 1.99.
- Engine tests no longer depend on whether a bundle is installed on the
  machine running them.

## [5.3.0] - 2026-09-22

The first ML verifiers, live. The `base` bundle now ships a model for the
entailment channel, so `groundlens.nli` runs after `bundle pull base`, and a
new sentence-similarity verifier runs on the same encoder as the lexical
channel.

### Added

- **`semantic.cosine`**, the semantic verifier: for each statement claim it
  pools a sentence vector for the claim and for every source and reports the
  highest cosine similarity as support, on the `base` bundle's encoder.
  `reproducible` under the pinned encoder. Similarity is not entailment, so it
  reports support but never a contradiction. Listed as an optional verifier in
  the default and AI-Act policies.
- **`base` bundle v2** carries a multilingual entailment model
  (`MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli`, exported to ONNX), so
  `groundlens.nli` (wired since 5.0) now runs from `bundle pull base`. The
  encoder feeds both the lexical and semantic channels.

### Changed

- **Windows CI** builds and tests only the abi3 floor (3.10) and newest (3.13)
  Python; the wheels are abi3, so the full four-version sweep on the slow
  Windows runners was redundant.
- **Releases are signed.** Each release binary gets a sigstore signature and the
  build gets SLSA provenance, attached to the GitHub Release as assets, so the
  release is verifiable offline (OpenSSF Signed-Releases).

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

[5.3.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v5.3.0
[5.2.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v5.2.0
[5.1.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v5.1.0
[5.0.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v5.0.0
[4.0.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v4.0.0
