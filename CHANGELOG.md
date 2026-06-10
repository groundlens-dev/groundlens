# Changelog

All notable changes to groundlens are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
groundlens uses [Calendar Versioning](https://calver.org/) with the format `YYYY.M.D`.

## 2026.6.10 -- `groundlens.agents`: per-agent rule sets for routing, RAG, and specialized agents

### Added

- **`groundlens.agents`** submodule: triage rule sets organized by the agent
  class they target. Modern AI systems are agentic pipelines, not single
  models. Each agent class has distinct failure modes and therefore distinct
  triage needs.
  - **`routing_rules()`** -- 10 rules across 4 sub-scores (intent_clarity,
    classification_confidence, fallback_appropriateness,
    disambiguation_quality) for intent classification agents. Citations
    include BBVA AI Factory's *Routing the future* (Falcón et al., 14/02/2025)
    and *AI Evaluation in the Age of Agents* (Torcal et al., 15/04/2026),
    Sarikaya et al. (IEEE TASLP 2014), Guo et al. (ICML 2017), Rao &
    Daumé III (ACL 2018), NIST AI RMF.
  - **`specialized_agent_rules()`** -- 9 rules across 4 sub-scores
    (entity_groundedness, entity_completeness, entity_calibration,
    execution_readiness) for tool-using / execution agents. Includes ISO
    13616 IBAN mod-97 verification and strict flag predicate suitable for
    agents that execute irreversible operations. Citations include the
    BBVA AI Factory Blue Eval post, ISO 13616, EBA Guidelines on the
    security of internet payments, and Federal Reserve SR 26-2.
  - **`rag_rules(domain="banking")`** -- agent-vocabulary alias for
    `groundlens_banking_rules()`. Signature forward-compatible with planned
    verticalizations (legal, healthcare, insurance).
- **Tagline update.** Package description: *"Triage for AI agents and model
  outputs. Deterministic. Auditable. No second LLM."*

### Changed

- `__init__.py` now exports `agents` submodule and the three new factories
  (`routing_rules`, `rag_rules`, `specialized_agent_rules`).
- README repositioned around "agent triage" while preserving the geometric
  layer messaging.

### Migration notes

- **Non-breaking.** All existing APIs continue to work unchanged.
- `rag_rules()` returns the same object as `groundlens_banking_rules()`
  today; callers can adopt the new name without behavioural change.

## 2026.6.9 -- `groundlens_banking_rules`: multi-source provenance rule set

### Added

- **`groundlens_banking_rules()`** factory: a new 20-rule reference set whose
  provenance is triangulated across five independent research tracks
  (peer-reviewed NLP literature, tier-1 bank public reports, banking regulator
  whitepapers, cross-industry frameworks, financial-domain NLP benchmarks).
  Rules are organized into five empirically-emergent sub-score categories:
  `groundedness`, `completeness`, `calibration`, `traceability`, `robustness`.
  Each rule carries a `citation` field pointing to its academic / industrial /
  regulatory provenance. The methodology and full per-rule provenance are
  documented in the companion paper *"Defendable Rules for LLM Rationale
  Evaluation in Banking Governance: A Multi-Source Provenance Framework"*
  (Marin, 2026).
- **`ChecklistRule.citation: str`** field (default `""`) for free-text
  provenance citation. Existing rules in `banking_rules()` retain their
  empty default; new rules in `groundlens_banking_rules()` populate it.
- **`RuleSet.sub_scores: tuple[str, ...]`** field (default
  `("spec", "expl", "bshift")`) makes the list of aggregated sub-score
  categories explicit and configurable per rule set.
- **`RuleSet.flag_predicate: Callable[[dict[str, float]], bool] | None`** field
  enables custom flag predicates per rule set. When `None`, the legacy
  predicate (`spec < quality_floor or expl < quality_floor`) is used.
- **`RuleSetResult.sub_scores: dict[str, float]`** canonical store for
  sub-score values. Convenience read accessors for the legacy categories
  (`spec`, `expl`, `bshift`) and for the current categories (`groundedness`,
  `completeness`, `calibration`, `traceability`, `robustness`) all read from
  this dict and return `0.0` when not defined by the active rule set.

### Changed

- **`RuleSet.evaluate()`** now iterates over `RuleSet.sub_scores` to aggregate
  weights, instead of hardcoding the three legacy categories. The geometric-
  mean quality is computed over all configured sub-scores.
- **`RuleSetResult`** is now a frozen dataclass with a `sub_scores: dict[str, float]`
  field instead of hardcoded `spec`, `expl`, `bshift` fields. Backward-compatible
  `@property` accessors preserve the legacy attribute interface — existing
  user code that reads `result.spec` / `result.expl` / `result.bshift`
  continues to work without modification.

### Backward compatibility

- **`banking_rules()`** continues to return a 3-category rule set
  (`spec`/`expl`/`bshift`) with the legacy 22 rules. No call-site changes
  required. The 20 existing tests in `test_rules.py` pass without modification.
- **Result-attribute access** via `result.spec`, `result.expl`, `result.bshift`
  is preserved via `@property` accessors on `RuleSetResult`.

### Notes for deployers

- A response evaluated with `groundlens_banking_rules()` produces a result
  whose `sub_scores` dict has keys `groundedness`, `completeness`,
  `calibration`, `traceability`, `robustness`. Legacy accessors
  (`result.spec`, etc.) return `0.0` because the current ruleset does not
  define those categories.
- The default flag predicate triggers on regulator-non-negotiable failures:
  `groundedness < 0.5 or calibration < 0.3 or traceability < 0.4`.

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
