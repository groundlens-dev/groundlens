# Changelog

All notable changes to GroundLens. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/). One version per release,
identical in the git tag and on PyPI.

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

[4.0.0]: https://github.com/groundlens-dev/groundlens/releases/tag/v4.0.0
