# Changelog

All notable changes to groundlens are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
groundlens uses [Calendar Versioning](https://calver.org/) with the format `YYYY.M.D`.

## 2026.6.25 -- Pluggable encoders, threshold fitting, default-model load fix

### Added

- **Pluggable encoder / bring-your-own-embeddings.** Every scoring entry
  point now accepts an `encoder=` keyword — a callable taking `list[str]`
  and returning an `(n, d)` array (e.g. `SentenceTransformer(...).encode`
  or a custom function). Provided on `compute_sgi`, `compute_dgi`,
  `calibrate`, `fit_thresholds`, and the `SGI` / `DGI` scorer classes. The
  custom-encoder path never imports sentence-transformers, so groundlens
  can score **without torch** when you bring your own embeddings or
  precomputed vectors.
- **`set_default_encoder` / `get_default_encoder`.** Register a
  process-global encoder once; all scoring routes through it regardless of
  how `encode_texts` was imported (no monkeypatching). Pass `None` to clear.
- **`fit_thresholds(...)` and `ThresholdFit`.** Fit SGI/DGI decision
  thresholds on a labeled set by maximizing Youden's J (`value >= threshold`
  implies grounded). No new dependencies — pure numpy.
- **Encoder/threshold mismatch warning.** Scoring with a non-default
  encoder or model while relying on the bundled thresholds / DGI `mu_hat`
  now emits a one-time `UserWarning` pointing you at
  `groundlens.fit_thresholds(...)` / `groundlens.calibrate(...)`. Default
  usage is unaffected.

### Fixed

- **`get_encoder` now passes `trust_remote_code=True` for the default
  Snowflake model** (`Snowflake/snowflake-arctic-embed-l-v2.0`), which ships
  custom pooling code and previously failed to load on a clean install. The
  behavior is resolved by `_resolve_trust_remote_code` (explicit override >
  known-model set > `GROUNDLENS_TRUST_REMOTE_CODE` env var > `False`), and
  the load gracefully falls back for older sentence-transformers releases
  that lack the kwarg.
- **Version sync.** `pyproject.toml` and `src/groundlens/_version.py` were
  out of step (2026.6.17 vs 2026.6.18); both are now `2026.6.25`.

## 2026.6.18 -- SGI bug fix + Snowflake default + paper alignment

### Fixed

- **`compute_sgi` now matches paper canonical formulation.** Previous
  implementation computed SGI as a Euclidean ratio over raw (non-normalized)
  embeddings:
  ```
  SGI_old = ||r - q|| / ||r - c||
  ```
  The published paper (arXiv:2512.13771, Algorithm 1) defines SGI as a ratio
  of **angular** distances over **L2-normalized** embeddings on the unit
  hypersphere:
  ```
  SGI = arccos(r_hat . q_hat) / arccos(r_hat . c_hat)
  ```
  The implementation has been corrected. Verified on RAGTruth (n=2,700) and
  RAGBench (n=8,838) with preserved embeddings: the two formulations produce
  rankings that differ by Δ AUROC ≤ 0.005 on contrastive encoders
  (Snowflake-L, MPNet, MiniLM, BGE, GTE). In practice flag decisions on these
  encoders were equivalent because contrastive training produces near
  unit-norm embeddings, making `2 sin(theta/2)` monotone in `theta`. The fix
  matters for non-contrastive or non-normalized encoders and aligns with the
  published algorithm.

### Changed

- **Default encoder is now `Snowflake/snowflake-arctic-embed-l-v2.0`.**
  Previous default was `all-MiniLM-L6-v2`. Snowflake Arctic Embed L v2.0 is:

  - **Multilingual** (100+ languages including Spanish/Catalan/Galician/
    English/Portuguese) — relevant for European bank deployments
  - **1024 dims, 568M params, 8192-token context** — better signal in
    long-context RAG scenarios
  - **Naturally L2-normalized output** — keeps the canonical angular SGI
    formulation numerically stable
  - **Calibrated in shipped cookbooks** and validated on RAGTruth + RAGBench

  The previous default is still exported as `LIGHTWEIGHT_MINILM` for
  CPU-only / latency-critical deployments. Override at scorer level:
  ```python
  from groundlens import SGI, LIGHTWEIGHT_MINILM
  sgi = SGI(model=LIGHTWEIGHT_MINILM)
  ```

### Removed

- **PGI (Perpendicular Grounding Index)** primitive was developed in
  intermediate builds of 2026.6.18 and **removed before release**.
  Cross-domain validation on RAGBench showed PGI does not generalize beyond
  RAGTruth-style hallucinations, and the underlying motivation (a precision
  "ceiling" of SGI ≈ 0.40 on RAGTruth) was traced to a structural property
  of the test dataset (mix of Type I and Type III hallucinations) rather
  than the primitive. The geometric taxonomy of Marin (2026,
  arXiv:2602.13224v3) predicts this: Type III (within-frame factual errors)
  are not detectable by angular geometry. See documented negative result on
  TruthfulQA in the SGI paper (AUC = 0.478).

### Docs

- README "What groundlens detects" section added with Type I/II/III taxonomy
  and citations to the three founding papers.
- Cookbook list reorganized: SGI/HaluEval-style examples vs DGI/calibrated
  examples vs Type III negative-result honest-limits documentation.

## 2026.6.17 -- `DGI.propose_labels` redesign with `SeedExample` (BREAKING)

### Breaking changes

- **`DGI.propose_labels` signature replaced.** The previous shape
  ``faq_corpus: list[str]`` + ``seed_pairs: list[tuple[str, str]]`` is
  gone. The new shape takes ``seeds: list[SeedExample]`` where each
  ``SeedExample(context=..., question=..., grounded=...)`` bundles the
  FAQ paragraph, the question, and the verified-grounded response. No
  deprecation alias -- the previous shape was released two days ago and
  was found to generate incoherent candidates in practice.

  **Why.** Under the old API, the candidate-generation loop sampled
  ``context`` and ``seed_pairs`` independently and at random. The
  resulting prompt routinely mixed a FAQ paragraph about one topic
  (e.g., hipoteca) with a seed pair about another (e.g., Bizum), and
  the LLM produced out-of-scope candidates that a human reviewer (or
  an LLM judge) labelled as junk. The fix binds the three fields
  together so the prompt is always coherent by construction. A
  regression test (`test_prompt_receives_matched_context_and_seed`)
  pins this behaviour.

- **Defaults adjusted.** ``n_candidates`` from 200 → 50 and
  ``n_to_label`` from 20 → 10. The new defaults take ≈5 minutes at
  4 s/call on OpenAI rather than ~15 minutes, which matters for the
  first interactive use of the API.

### Added

- **`SeedExample` dataclass.** Frozen, validated. Empty or
  whitespace-only fields raise ``ValueError`` at construction time,
  before any LLM calls are issued. Exposed at the top of the package
  alongside ``ProposedLabel`` and ``PropositionBatch``.

### Changed

- **`docs/guides/active-learning.md` rewritten** from scratch in
  plain language with a three-step flow (gather seeds → call
  ``propose_labels`` → label and calibrate), an explicit
  troubleshooting section, and a "stop when AUROC plateaus" rule.
- **README "Bootstrap your calibration set" section condensed** to
  one snippet around `SeedExample`, with a three-sentence mental
  model up front.

### Migration

```python
# Before (2026.6.16, removed)
batch = dgi.propose_labels(
    faq_corpus=[paragraph_a, paragraph_b, ...],
    seed_pairs=[(q1, r1), (q2, r2), ...],
    llm_generate=my_llm,
    n_candidates=200,
    n_to_label=20,
)

# After (2026.6.17)
from groundlens import SeedExample

batch = dgi.propose_labels(
    seeds=[
        SeedExample(context=paragraph_a, question=q1, grounded=r1),
        SeedExample(context=paragraph_b, question=q2, grounded=r2),
        # ...
    ],
    llm_generate=my_llm,
    n_candidates=50,    # new default
    n_to_label=10,      # new default
)
```

## 2026.6.16 -- active-learning bootstrap (`DGI.propose_labels`)

### Added

- **`DGI.propose_labels()` — bootstrap a verified-grounded calibration
  set with active learning.** New method on the `DGI` class that
  generates candidate `(question, response)` pairs via a user-supplied
  `llm_generate` callable, scores them with the current DGI `mu_hat`,
  and returns the `n_to_label` most useful candidates for a human
  reviewer. Acquisition combines 70% uncertainty (distance to the
  median seed score) with 30% strategy diversity. The method does NOT
  label and does NOT calibrate -- the human reviewer assigns labels,
  and the caller passes the labelled pairs back to `DGI.calibrate()`.
  This keeps the loop non-circular by design.
- **Five confabulation strategies from
  ``groundlens-dev/grounding-benchmark``** (CC BY 4.0) shipped as
  `groundlens._internal.strategies.DEFAULT_STRATEGIES`:
  `redefinition`, `mechanism_inversion`, `entity_composition`,
  `polysemy`, `template_filling`. Each strategy preserves a different
  subset of the distributional properties that embedding models
  encode while violating referential truth. Custom strategies are
  supported via `(name, prompt_template)` tuples.
- **New public dataclasses `ProposedLabel` and `PropositionBatch`**
  exposed from the top-level package. `PropositionBatch.review_template`
  is a ready-to-send Markdown checklist for the human reviewer.

### API

```python
from groundlens import DGI

dgi = DGI()  # bundled cross-domain calibration
batch = dgi.propose_labels(
    faq_corpus=[...],            # the deployment's FAQ paragraphs
    seed_pairs=[(q, a), ...],    # 10-50 verified grounded pairs
    llm_generate=my_llm_call,    # any callable (prompt: str) -> str
    n_candidates=200,
    n_to_label=20,
    strategies="default",        # or tuple of names or custom pairs
)
# Hand batch.review_template to a human reviewer; collect labels;
# pass the labelled grounded pairs to dgi.calibrate(pairs=...) for the
# next round.
```

### Notes

- `propose_labels` is a method on `DGI` (not a top-level function and
  not a `bootstrap` submodule). SGI is a geometric ratio with no
  calibration parameter, so the active-learning loop applies only to
  DGI.
- `llm_generate` failures surface as `RuntimeWarning` and the failed
  candidate is skipped; the batch returns whatever succeeded.

## 2026.6.15 -- bundled calibration upgrade, dependency pin fix, banking-corpus removal

### Changed

- **Bundled `reference_pairs.csv` upgraded from 20 to 212 verified pairs.**
  The new corpus is the open `groundlens-dev/grounding-benchmark`
  dataset (CC BY 4.0) covering nine domains: python_coding (47),
  finance (40), medical (40), science (21), typescript_coding (18),
  history (14), law (11), general (11), geography (10). Each row is a
  ``(question, grounded_response, fabricated_response)`` triple with
  the fabricated response written by a non-expert human from memory
  (human confabulations, not LLM-generated). The previous 20-pair
  bundled corpus was too narrow to act as a generic ``mu_hat``
  reference direction; the new corpus reaches a more representative
  ``mu_hat`` out of the box.
- **`_load_bundled_csv` now auto-detects delimiter** (comma or
  semicolon) using the same heuristic as the user CSV loader. The
  upgraded `reference_pairs.csv` is comma-delimited (the previous
  bundled CSV was semicolon-delimited); user CSVs in either delimiter
  continue to load unchanged.
- **`sentence-transformers` upper bound raised**
  (`>=2.7.0,<6.0.0` from `>=2.7.0,<4.0.0`). The previous upper bound
  forced a cascade downgrade of `transformers`, `huggingface-hub`, and
  `sentence-transformers` when installing on Python environments that
  already had the current major releases. The new bound covers
  versions 4.x and 5.x without breaking changes observed in
  groundlens's usage of the encoder (`encode(..., convert_to_numpy=True,
  normalize_embeddings=False)`).

### Removed

- **`groundlens.data.banking_reference_pairs_path` and the bundled
  `banking_reference_pairs.csv`** (the 26-pair banking corpus shipped
  in 2026.6.7). The corpus was too small to be useful as a
  banking-domain calibration on its own, and shipping it created an
  impression of out-of-the-box banking accuracy that the corpus could
  not back. Banking deployments should build their own
  verified-grounded calibration corpus (100–500 pairs per sub-domain)
  and pass it via ``reference_csv=`` to ``compute_dgi`` /
  ``compute_sgi`` / ``DGI``. The migration is a one-line code change.

### Migration notes

- **Breaking change for callers of `banking_reference_pairs_path`.**
  Replace
  ``compute_dgi(..., reference_csv=str(banking_reference_pairs_path()))``
  with
  ``compute_dgi(..., reference_csv="/path/to/your/banking_calibration.csv")``
  pointing at a deployment-specific verified-grounded corpus. If you
  need a temporary fallback, omit ``reference_csv`` to use the bundled
  cross-domain corpus — a generic starting point, not a substitute for
  a banking-specific corpus.
- **Non-breaking for users of `reference_pairs_path()` and
  `compute_dgi(reference_csv=None)`.** The default ``mu_hat`` now
  reflects 212 cross-domain grounded pairs instead of 20. Numeric
  scores will shift; recalibrate threshold percentiles on a current
  production sample after upgrading.
- **Non-breaking for the `sentence-transformers` pin change.** All
  versions in `[2.7.0, 6.0.0)` are accepted.

### References

- Marin, J. (2026). *A Methodology for Building Human-Confabulated
  Hallucination Benchmarks*.
  [`groundlens-dev/grounding-benchmark`](https://github.com/groundlens-dev/grounding-benchmark).
  CC BY 4.0.

## 2026.6.14 -- multilingual encoder constants for European customer-attention deployments

### Added

- **`MULTILINGUAL_MINI`** = `"paraphrase-multilingual-MiniLM-L12-v2"`. Named
  constant for the recommended multilingual sentence-transformer model for
  European-bank customer-attention channels (WhatsApp, mobile app, web chat)
  that operate across Spanish, Catalan, Galician, Basque, and English. 118M
  params, 384 dims, 50+ languages. Sub-second on CPU. Pass it as
  `DGI(model=MULTILINGUAL_MINI)` or `compute_sgi(..., model=MULTILINGUAL_MINI)`.
- **`MULTILINGUAL_E5`** = `"intfloat/multilingual-e5-large"`. Named constant
  for the higher-quality multilingual encoder (560M params, 1024 dims,
  100+ languages). ~5x inference cost vs `MULTILINGUAL_MINI`; recommended
  for batch evaluation, audit replay, or environments where the latency
  budget allows it. Note the model card recipe (`"query: "` / `"passage: "`
  prefixes) must be applied at the call site if used.
- **`DEFAULT_MODEL`** is now also re-exported at the top level for symmetry
  with the multilingual constants (the constant existed in
  `groundlens._internal.embeddings` but was not importable from
  `groundlens`).

### Changed

- **`__all__`** in `groundlens.__init__` extended with `DEFAULT_MODEL`,
  `MULTILINGUAL_MINI`, `MULTILINGUAL_E5`.

### Migration notes

- **Non-breaking.** The constants are additive. The string values they expose
  have always been accepted as `model=...` arguments to `compute_sgi`,
  `compute_dgi`, and `DGI` -- this release only assigns them named identifiers
  and documents the recommended deployment recipe for multilingual customer
  attention.

## 2026.6.13 -- archetype as function, dimensions as kwargs (Phases 1 + 2)

### Changed (no behaviour change for current call sites)

- **`customer_support_rag_rules()` → `customer_support_rules()`.**
  The canonical name drops the `_rag_` infix because RAG vs no-RAG is now a
  kwarg. `customer_support_rag_rules()` is preserved as a
  `DeprecationWarning` alias that returns a `RuleSet` byte-for-byte
  identical to the legacy 2026.6.11 / 2026.6.12 output (same name field
  `"customer_support_rag_v1"`, same rules, same weights, same flag
  predicate). Cookbook deployers can keep their import for now; the
  warning points at the new name.

- **`groundlens_banking_rules()` → `decision_rationale_rules()`.**
  The 20-rule banking decision-rationale set is reachable under its
  archetype name. `groundlens_banking_rules()` continues to work and
  returns the same `RuleSet` with the legacy `"groundlens_banking_v1"`
  name; the new factory returns the same rules under
  `"decision_rationale_v1_finance"`. Both are exported at the top level.

- **`rag_rules()` deprecated.** The semantically confusing dispatcher
  (`rag_rules(domain="banking")` returned a *decision-rationale* set, not
  a *RAG* set) is preserved as a deprecated alias that redirects to the
  appropriate archetype factory and emits a `DeprecationWarning`.

### Added

- **`customer_support_rules(rag=True, domain="general", language="en")`.**
  - `rag=False` shrinks the produced sub-scores to
    `("completeness", "no_overreach")` because there is no context to
    verify against. The flag predicate adapts to the smaller taxonomy.
  - `domain="finance" | "healthcare" | "legal"` extends the stopword and
    speculative-procedure marker vocabulary so the no-overreach check
    catches domain-specific patterns ("co-pay tier", "retainer agreement",
    "private banking tier", etc.). Does not add or remove rules.
  - `language="es" | "multi"` adds Spanish speculative markers and a
    Spanish-aware legal-reference regex (`Ley`, `Real Decreto`,
    `Artículo`, etc.).

- **`decision_rationale_rules(domain="finance", regulations=(), quality_floor=0.3)`.**
  - `domain` validated against `("finance",)`; non-finance verticals
    raise `ValueError` rather than silently returning the finance set.
  - `regulations` accepts validated keys
    (`"eu_ai_act"`, `"sr_26_2"`, `"sr_11_7"`, `"nist_ai_600_1"`,
    `"nist_ai_rmf"`, `"iso_42001"`, `"ecb_internal_models"`,
    `"eba_gl_2020_06"`, `"pra_ss1_23"`, `"hipaa"`, `"gdpr"`).
    *Implementation note*: in 2026.6.13 the kwarg is accepted and
    validated, but the provenance-filtered rendering of
    `audit_explanation` is reserved for a follow-up release. A
    `UserWarning` is emitted when the kwarg is non-empty.

- **`routing_rules(domain="general")`** and
  **`specialized_agent_rules(domain="general", tools=())`** accept the
  new kwargs for API symmetry. No behavioural change.

- **ADR 0001** (`docs/adr/0001-rule-set-architecture.md`) documenting the
  decision rationale, the alternatives considered, and the deprecation
  schedule.

### Migration

- Non-breaking. Every call site that compiled against 2026.6.11 / 2026.6.12
  still compiles and produces identical output. The only observable
  difference is the `DeprecationWarning` on legacy factory names.
- Recommended migration order for deployers:
  1. Replace `customer_support_rag_rules()` with `customer_support_rules()`.
  2. Replace `groundlens_banking_rules()` with
     `decision_rationale_rules(domain="finance")`.
  3. Replace `rag_rules(domain="banking")` with
     `decision_rationale_rules(domain="finance")`, and
     `rag_rules(domain="customer_support")` with
     `customer_support_rules(rag=True)`.

## 2026.6.12 -- repositioning: *Verifiable agent triage* + generic-source citations

### Changed

- **Tagline:** *Verifiable agent triage.* Package description and top-level
  docstring updated. README rewritten from scratch around the positioning that
  geometry + rules together are what survives a model risk audit; neither
  layer alone is enough.
- **README:** new structure — Why geometry AND rules, Quick start (SGI + rules
  / DGI + rules combined), Built-in rule sets table, SGI/DGI calibration
  workflow, Build your own rule set, end-to-end LangChain pipeline with
  hash-chained audit log.
- **Rule citations in `groundlens.agents`** (customer_support, routing,
  specialized) reworded from specific industry-author citations to
  generic-source descriptors (e.g. *"Industry banking RAG evaluation framework
  — relevance check"*). The underlying rule logic, weights, sub-scores, and
  flag predicates are unchanged. Audit trails produced by `RuleSet.evaluate`
  still cite a source per rule; the citation strings are now
  vendor-/institution-neutral.
- **Docstrings** in `agents/__init__.py`, `agents/customer_support.py`,
  `agents/rag.py`, `agents/routing.py`, `agents/specialized.py` updated to
  drop industry-specific archetype names in favor of generic agent-class
  descriptors.

### Migration notes

- **Non-breaking.** All public APIs, factory names, rule IDs, sub-scores, and
  flag predicates are identical to 2026.6.11.
- Audit trails emitted by `RuleSet.evaluate` will show updated citation
  strings; downstream code that parses citations literally should be reviewed,
  but no API contract has changed.

## 2026.6.11 -- `customer_support_rag_rules`: domain-fit rule set for informational customer-support agents

### Added

- **`customer_support_rag_rules()`** factory: a 7-rule set for customer-support
  RAG agents (the BBVA Blue archetype) across 3 sub-scores: `groundedness`,
  `completeness`, `no_overreach`. Designed for informational responses over a
  FAQ knowledge base, where failure modes are fabricated numbers, fabricated
  proper nouns, and procedural overreach -- not the rationale-cite-source-span
  pattern that `groundlens_banking_rules` is calibrated for. Flag predicate is
  non-compensatory on `groundedness` and `no_overreach`; `completeness` is
  surfaced as UX feedback without tripping the safety flag.
- **`rag_rules(domain="customer_support")`**: dispatches to the new factory.
  Existing `rag_rules()` and `rag_rules(domain="banking")` calls continue to
  return `groundlens_banking_rules()` unchanged.
- **README:** new "Build your own rule set" section with a 4-step recipe and
  a full minimal example, plus a guides/custom-rule-sets.md companion.

### Changed

- `groundlens.agents.__init__` exports `customer_support_rag_rules`.
- Package-level `groundlens.__init__` re-exports the new factory for top-level
  import.

### Migration notes

- **Non-breaking.** All existing APIs continue to work unchanged. `rag_rules()`
  still returns the banking ruleset by default.

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
