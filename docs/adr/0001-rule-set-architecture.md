# ADR 0001 — Rule set architecture: archetype as function, dimensions as kwargs

**Status:** Accepted
**Date:** 2026-06-15
**Deciders:** Javier Marín
**Releases affected:** 2026.6.13 (Phase 1 + 2)

## Context

Groundlens ships rule sets in `groundlens.agents` for the three agent classes
in production AI pipelines (routing, RAG/informational, specialized/tool-using)
plus a decision-rationale set in `groundlens.rules`
(`groundlens_banking_rules`). The earlier naming convention encoded both the
**agent archetype** and the **deployment dimension** in the function name:

```
customer_support_rag_rules()    # archetype + modality (RAG/no-RAG) baked in
groundlens_banking_rules()      # archetype + domain (banking) baked in
rag_rules(domain=...)           # dispatcher that returned the banking set by default
```

Two real cases (BBVA Blue RAG, Santander decision rationales — both in the
cookbook) confirmed the current rule sets work, but they also surfaced three
problems:

1. **Proliferation pressure.** Adding insurance, healthcare, legal coverage
   under the current convention would require one new factory per domain.
2. **Confusing dispatch.** `rag_rules(domain="banking")` returned a
   decision-rationale set, not a RAG set. The name and the semantics
   disagreed.
3. **Modality baked in.** `customer_support_rag_rules` could not be reused
   for the no-RAG case (chat without retrieved context) without cloning.

## Decision

**Archetype is the function name. Dimensions are kwargs.**

```python
customer_support_rules(rag=True, domain="general", language="en")
decision_rationale_rules(domain="finance", regulations=("eu_ai_act",))
routing_rules(domain="general")
specialized_agent_rules(domain="finance", tools=())
```

- One factory **per agent archetype** (routing, customer support, decision
  rationale, specialized).
- Dimensions that the archetype legitimately varies over become **keyword
  arguments** on that factory.
- Heuristic for adding a new factory: only when the new agent class has a
  **structurally distinct sub-score taxonomy**. Same sub-scores with a
  different vocabulary is a kwarg, not a function.

### Heuristic table

| Change | Action | Why |
|---|---|---|
| New agent **archetype** (different sub-scores) | New factory | Structurally distinct |
| New **domain** (banking → insurance → healthcare) | `domain=` kwarg | Sub-scores stable; vocabulary changes |
| New **regulation** (EU AI Act → SR 26-2 → HIPAA) | `regulations=` filter on `audit_explanation` | Rules unchanged; only citation provenance changes |
| New **language** (en → es → multi) | `language=` kwarg | Stopword / speculative-marker surface only |
| **RAG present vs absent** | `rag=` kwarg | Same archetype, different evidence available |

## Alternatives considered

### Approach 1 — Single generic factory

```python
rule_set(archetype="customer_support", rag=True, domain="finance", ...)
```

Rejected: less discoverable. IDE autocomplete on a function name gives the
deployer the archetype catalogue immediately; autocomplete on a kwarg of a
generic factory doesn't.

### Approach 2 — Functional composition

```python
customer_support_base_rules().extend(finance_extension()).extend(eu_ai_act_extension())
```

Rejected: more verbose at the call site. The 95% path should be one line, not
three. Composition is Pythonic but punishes the deployer reading a notebook at
11 PM. Could be reintroduced as a power-user API later.

### Approach 4 — Minimal kwargs, keep current names

Rejected by the maintainer on UX grounds: keeping both
`customer_support_rag_rules` and a hypothetical `customer_support_rules`
factory side by side is worse than collapsing them into one with `rag=` as a
parameter. The cost of the refactor is justified by the UX win.

## Consequences

### Phase 1 (release 2026.6.13)

- `customer_support_rag_rules()` → `customer_support_rules(rag=True, domain="general", language="en")`.
- Old name preserved as a `DeprecationWarning` alias for at least three
  releases.
- `rag=False` shrinks the produced sub-scores: `groundedness` is omitted
  (no context to verify against); the result carries `completeness` and
  `no_overreach` only. The flag predicate adapts.
- `domain` and `language` extend stopwords / speculative markers; they do
  not add rules.

### Phase 2 (same release 2026.6.13)

- `groundlens_banking_rules()` → `decision_rationale_rules(domain="finance", regulations=("eu_ai_act", "sr_26_2"))`.
- Old name preserved as a `DeprecationWarning` alias.
- `regulations=` filters the citation lines that appear in
  `audit_explanation`; it does not add or remove rules.
- `rag_rules()` (the old dispatcher) is preserved as a deprecated alias that
  redirects to `customer_support_rules(rag=True)` for the `customer_support`
  case and `decision_rationale_rules(domain="finance")` for the `banking`
  case.
- `routing_rules()` gains a `domain="general"` kwarg for symmetry; no
  behavioural change yet.
- `specialized_agent_rules()` gains `domain="general"` and `tools=()`
  kwargs.

### Cookbook

Both notebooks (`customer_support_rag_eval_clean.ipynb`,
`decision_rationale_eval.ipynb`) are updated to use the new factory names.
The deprecated calls would still work but emit a warning.

### Phase 3 (future)

Removal of deprecated aliases is deferred to a future release. No date set;
will follow an explicit notice on the changelog.

## Non-decisions (left for later)

- **`template=` parameter for `compute_sgi` / `compute_dgi`** is orthogonal
  to this refactor. It belongs to the geometric layer, not the rule layer.
  Tracked separately.
- **Power-user composition API** (`.extend()`) is not introduced here.
  Reconsider only if a real case requires it.
- **`register_domain()` extension hook** is not introduced here. Reconsider
  if community contributions start arriving.

## References

- Cookbook notebook 1 (BBVA RAG Blue replication):
  `customer_support_rag_eval_clean.ipynb`
- Cookbook notebook 2 (Santander decision rationale replication):
  `decision_rationale_eval.ipynb`
- Marin (2025). *Semantic Grounding Index for LLM Hallucination Detection.*
  arXiv:2512.13771.
- Marin (2026). *A Geometric Taxonomy of Hallucinations in Large Language
  Models.* arXiv:2602.13224.
- Marin (2026). *Defendable Rules for LLM Rationale Evaluation in Banking
  Governance: A Multi-Source Provenance Framework.*
