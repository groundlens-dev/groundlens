# Changelog

All notable changes to groundlens are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
groundlens uses [Calendar Versioning](https://calver.org/) with the format `YYYY.M.D`.

## 2026.6.8 -- DGI inline calibration fix + lint hygiene

### Fixed

- **DGI inline calibration silently ignored:** `DGI.calibrate(pairs=...)` populated
  the inline `mu_hat` under the cache key `(model, "__inline__")`, but
  `DGI.score()` then passed `reference_csv=None` to `compute_dgi`, which looks
  up `(model, "__bundled__")` — so the inline calibration was never applied
  and every call fell through to the bundled reference direction. Fix: pass
  `self.reference_csv` through unchanged. Now `_get_mu_hat` resolves `None →
  bundled`, real path → load CSV, and `"__inline__"` → inline cache hit.
  Added defensive guard in `_get_mu_hat` to raise a clear `RuntimeError` if
  `compute_dgi(reference_csv="__inline__")` is called without prior `calibrate()`.
- **Lint hygiene across 2026.6.7 modules:** Removed 64 unused `# noqa: ARG001`
  directives from `rules.py` (the ARG ruleset isn't enabled), moved
  `collections.abc` imports to `TYPE_CHECKING` blocks in `rules.py` and
  `audit.py`, replaced `try/except sqlite3.Error/pass` with
  `contextlib.suppress(sqlite3.Error)` in `audit.AuditLog.close`, added
  docstrings to `__enter__` / `__exit__` / `__del__`, removed unused
  imports in `tests/unit/test_rules.py`, fixed one over-long line.

### Added

- **`tests/integration/test_dgi_inline_calibration.py`:** Regression tests
  for the DGI inline-calibration fix. Verifies inline scores differ from
  bundled on the same input, that the inline cache key is populated, and
  that the two error paths raise a clear `RuntimeError`.

## 2026.6.7 -- AI Governance tool uplift

### Added

- **`groundlens.rules`:** Rule-based interpretable layer. Checklist-style
  rules producing specificity / explanatory linkage / boundary shift
  sub-scores per evaluation, with per-rule evidence spans surfaced in a
  multi-line audit explanation. Bundled `banking_rules()` factory covers
  22 rules across the three sub-scores. Deterministic, no LLM. New
  public types: `RuleSet`, `ChecklistRule`, `RuleEvidence`, `RuleResult`,
  `RuleSetResult`.
- **`groundlens.compliance`:** Standards mapping and audit-report
  generation. `@maps_to(...)` decorator attaches a `ComplianceMapping`
  to a function declaring which clauses of SR 11-7, EU AI Act, and NIST
  AI RMF the implementation was designed to support. Pre-defined
  mappings for `compute_sgi`, `compute_dgi`, `banking_rules`, and the
  audit log. `ComplianceReport.to_markdown()` renders an examiner-ready
  report combining summary statistics and explicit clause references.
- **`groundlens.audit`:** Hash-chain immutable audit log backed by SQLite.
  Each entry's SHA-256 hash links to its predecessor; any post-hoc
  modification breaks `verify_chain()`. `AuditLog.export_jsonl()` produces
  examiner-ready exports. Single-writer single-process by design.
- **Banking calibration corpus:** `src/groundlens/data/banking_reference_pairs.csv`
  with 25 verified pairs across credit, AML, KYC, fraud, sanctions,
  concentration, and model risk sub-domains. Accessible via
  `from groundlens.data import banking_reference_pairs_path`.
- **`docs/guides/sr-11-7.md`:** SR 11-7 compliance guide covering §3
  Model Validation, §5 Documentation, §6 Vendor Models, and §7 Governance.
- **`docs/guides/nist-ai-rmf.md`:** NIST AI RMF mapping across the
  Govern / Map / Measure / Manage functions.
- **`docs/guides/banking-deployment.md`:** End-to-end deployment guide
  for regulated banking environments — minimum viable pipeline,
  hybrid (geometric + rules) flagging, calibration, threshold tuning,
  self-hosted setup, examiner readiness checklist.

### Changed

- **README:** Added three rows to the "I want to..." table linking to
  the banking-deployment, SR 11-7, and NIST AI RMF guides.
- **mkdocs nav:** New guides registered under Guides section.

## 2026.5.22 -- LangGraph context propagation fix

### Fixed

- **LangGraph reporter always DGI-flagged:** Expanded context capture keys to include intermediate state keys (`synthesis`, `summary`, `answer`, `response`, `output`, `result`). Each node's output is legitimate grounding context for the downstream node — the synthesizer's output is context for the reporter, just as the retriever's output is context for the synthesizer. The previous fix was too aggressive: it prevented SGI inflation by blocking ALL intermediate outputs, but this caused the reporter to always fall back to DGI with near-zero scores on correct answers. Safe because `on_chain_end` fires after the node's own LLM call, so a node can never score against its own output.

## 2026.5.21 -- LangGraph integration fixes

### Fixed

- **LangGraph callback `on_chain_start` crash:** Guard against `serialized=None` parameter that some LangGraph chain types pass.
- **LangGraph context flow (all-DGI bug):** Retriever nodes produce context via chain state updates, not tool callbacks. Added node tracking via `_node_run_ids` and context capture in `on_chain_end` so subsequent LLM calls get SGI scoring.
- **Reporter SGI inflation:** Removed fallback context capture that was storing synthesizer output as reporter context, inflating SGI to meaningless values (5.8–10.0). Now only priority keys (`context`, `documents`, `retrieved_docs`, `search_results`) are captured.
- **Notebook render error:** Removed stale `metadata.widgets` from notebook JSON that caused "missing 'state' key" render failures.
- **Dallas retriever word matching:** Changed from substring match to all-words match so `"dallas_capital"` matches queries like "what is the capital of the state where dallas is located."

### Changed

- **Notebook restructure:** All installs and imports consolidated at the top. Clear API key setup instructions (HF_TOKEN + OPENAI_API_KEY) added at the beginning.

## 2026.4.22 -- Initial release

### Added

- **SGI (Semantic Grounding Index):** context-required hallucination detection via embedding distance ratios. Implements the method from arXiv:2512.13771.
- **DGI (Directional Grounding Index):** context-free hallucination detection via directional alignment with a calibrated reference direction. Implements the method from arXiv:2602.13224v3.
- **`evaluate()` and `evaluate_batch()`:** high-level API that auto-selects SGI (when context is provided) or DGI (when context is absent).
- **Domain calibration:** `calibrate()` function and `CalibrationResult` for computing domain-specific DGI reference directions. 20-100 verified pairs improve AUROC from ~0.76 to 0.90-0.99.
- **Result types:** `SGIResult`, `DGIResult`, and `GroundlensScore` frozen dataclasses with scores, flags, and human-readable explanations.
- **CLI:** `groundlens check`, `groundlens evaluate`, `groundlens calibrate`, `groundlens benchmark` commands.
- **LLM providers:** OpenAI, Anthropic, and Google Generative AI wrappers with automatic hallucination scoring on every response.
- **Framework integrations:** LangChain evaluator and callback, CrewAI tool, Semantic Kernel filter, AutoGen checker.
- **Geometry layer:** Euclidean distance, displacement vectors, unit normalization, cosine similarity, and mean direction computation.
- **Threshold system:** Empirically derived decision boundaries with tanh (SGI) and linear (DGI) normalization to [0, 1].
- **Default model:** `all-MiniLM-L6-v2` (sentence-transformers). No GPU required.
- **Full type coverage:** mypy strict mode, all public APIs fully annotated.
- **Test suite:** unit tests (no model loading), integration tests, provider tests, and integration framework tests.
