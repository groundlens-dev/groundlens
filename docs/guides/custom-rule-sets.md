# Build your own rule set

The Groundlens rule engine is intentionally small. `RuleSet` and `ChecklistRule` are composable primitives — you write the rules, Groundlens runs them deterministically and produces an audit trail with citations.

This guide walks through the full workflow: anatomy, the 4-step recipe, a complete worked example, patterns, and common pitfalls.

## When you need a custom rule set

The bundled rule sets cover four agent archetypes. The naming convention since release **2026.6.13** follows ADR 0001: the **archetype** is in the function name, the **deployment dimensions** are keyword arguments.

| Bundled set | Purpose | Use when |
|---|---|---|
| `decision_rationale_rules(domain="finance", regulations=())` | Decision rationales | Credit / AML / KYC / fraud / sanctions decisions with auditable rationale |
| `customer_support_rules(rag=True, domain="general", language="en")` | Informational customer-facing agents | FAQ-RAG (`rag=True`) or chat-without-context (`rag=False`). Domain widens the stopword vocabulary; language switches the speculative-marker + legal-reference patterns. |
| `routing_rules(domain="general")` | Intent classification agents | Multi-class routing with fallback and clarify |
| `specialized_agent_rules(domain="general", tools=())` | Tool-using / execution agents | Entity capture, transaction execution |

**Deprecated aliases preserved for backwards compatibility:**

| Legacy name | New canonical call |
|---|---|
| `customer_support_rag_rules()` | `customer_support_rules(rag=True)` |
| `groundlens_banking_rules()` | `decision_rationale_rules(domain="finance")` |
| `rag_rules(domain="banking")` | `decision_rationale_rules(domain="finance")` |
| `rag_rules(domain="customer_support")` | `customer_support_rules(rag=True)` |

Build your own when none of these fits — legal review, insurance claims, clinical decision support, internal governance, custom verticals. Or extend an existing one with domain-specific reinforcements.

## Anatomy

A rule set is five pieces.

### 1. `check` function

A pure function with this signature:

```python
def check_something(question: str, response: str, context: str | None, metadata: dict) -> RuleEvidence:
    ...
```

Pure means: same input → same output, no side effects, no LLM calls, no network. Deterministic pattern matching, regex, length checks, presence/absence tests, calls to external deterministic validators (e.g. ISO 13616 IBAN mod-97).

Return a `RuleEvidence` describing what was checked.

### 2. `RuleEvidence`

```python
RuleEvidence(matched=True | False, span="<what triggered the match>", explanation="<one short sentence>")
```

- `matched` — did the rule fire as a pass?
- `span` — the substring or fact that triggered the match (for audit trail readability)
- `explanation` — one short sentence describing what was checked

### 3. `ChecklistRule`

One rule with a weight on one sub-score.

```python
ChecklistRule(
    id="legal.cites_clause",           # stable identifier
    description="rationale cites a specific contract clause",
    weight=0.60,                       # weight on the sub_score
    sub_score="traceability",          # which sub-score this rule contributes to
    check=check_cites_clause,          # the check function
    citation="EU AI Act 2024/1689 Art. 13(3)(b)(iv)",
)
```

**Citations matter.** Every defendable rule has a citation to an academic, industrial, or regulatory source that motivates it. When an auditor asks "why this threshold?", you point at the source. Empty citation is allowed but discouraged.

### 4. Sub-scores

A tuple of sub-score category names. Rules whose `sub_score` matches a name in this tuple contribute to that sub-score's aggregated weight. Rules outside the tuple are recorded in the audit but excluded from aggregation.

```python
sub_scores = ("groundedness", "traceability")
```

### 5. Flag predicate (optional)

A function that decides whether the aggregated result is flagged for human review.

```python
def flag_predicate(sub_scores: dict[str, float]) -> bool:
    return sub_scores.get("groundedness", 0.0) < 0.5
```

**Non-compensatory by default.** A typical predicate flags if any one safety-relevant sub-score collapses below a threshold. Don't let high scores on UX dimensions mask low scores on safety dimensions.

## The 4-step recipe

### Step 1 — Decide the sub-scores

What dimensions matter in your domain? Start from the five-category template:

- `groundedness` — does the response stay anchored in the provided context?
- `completeness` — does the response cover what was asked?
- `calibration` — does the response hedge appropriately?
- `traceability` — can a human auditor reconstruct the reasoning?
- `robustness` — does the response survive adversarial or noisy inputs?

Add domain-specific dimensions when needed. The customer-support rule set uses `(groundedness, completeness, no_overreach)`. The routing rule set uses `(intent_clarity, classification_confidence, fallback_appropriateness, disambiguation_quality)`.

### Step 2 — Write check functions

One per rule. Keep them small and single-purpose. Each check should be testable in isolation.

```python
def check_cites_clause(question, response, context, metadata):
    matched = "clause" in response.lower() or "§" in response
    return RuleEvidence(
        matched=matched,
        span="clause/§",
        explanation="rationale cites a specific contract clause",
    )
```

### Step 3 — Assemble `ChecklistRule` instances

Give each rule:

- A stable `id` namespaced to your domain (`legal.cites_clause`, not just `cites_clause`)
- A weight summing to roughly 1.0 per sub-score (not strict — sub-scores are capped at 1.0)
- A `sub_score` that appears in your `sub_scores` tuple
- A `citation` to the source that justifies the rule

### Step 4 — Wrap in a `RuleSet`

```python
ruleset = RuleSet(
    name="legal_contract_review_v1",
    rules=rules,
    sub_scores=("groundedness", "traceability"),
    flag_predicate=flag_predicate,
)
```

Run it:

```python
result = ruleset.evaluate(
    question="Is this termination valid?",
    response="Under clause 4.2, 30 days notice is sufficient...",
    context="Section 4.2 Termination. Either party may terminate...",
    metadata={},
)
```

You get back a `RuleSetResult` with:

- `sub_scores: dict[str, float]` — capped weight sums per category
- `quality: float` — geometric mean of all sub-scores
- `flagged: bool` — output of the flag predicate
- `rule_results: tuple[RuleResult, ...]` — one entry per rule, with `matched`, `evidence_span`, `explanation`
- `audit_explanation: str` — multi-line human-readable trail suitable for log inclusion

## Patterns

### External validators

Rules can call out to deterministic external validators — ISO standards, business rules engines, regex libraries. The check function stays pure (deterministic and side-effect-free); the validator does the work.

```python
def _iban_valid_format(iban: str) -> bool:
    """ISO 13616 mod-97 verification."""
    cleaned = re.sub(r"\s+", "", iban).upper()
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$", cleaned):
        return False
    rearranged = cleaned[4:] + cleaned[:4]
    converted = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
    return int(converted) % 97 == 1

def check_iban_format_valid(question, response, context, metadata):
    iban = metadata.get("entities", {}).get("iban")
    if not iban:
        return RuleEvidence(matched=True, span="", explanation="no IBAN — rule does not apply")
    matched = _iban_valid_format(str(iban))
    return RuleEvidence(
        matched=matched,
        span=str(iban)[:8] + "...",
        explanation="captured IBAN passes ISO 13616 format check",
    )
```

### Abstention vs. failure

When a rule does not apply (e.g. "IBAN format" rule on a response with no IBAN), return `matched=True` with an explanation that includes "abstains" or "rule does not apply". Sub-scores cap at 1.0, so abstention does not punish the score.

A rule should abstain — not fail — when its precondition isn't met.

### Non-compensatory flagging

Don't average across safety and UX dimensions in your flag predicate. A response that is "75% correct on safety, 100% on UX" should still be flagged.

```python
def flag_predicate(sub_scores):
    return (
        sub_scores.get("groundedness", 0.0) < 0.5
        or sub_scores.get("no_overreach", 0.0) < 0.5
    )
```

### Sub-score weights

Within a sub-score, weights should roughly sum to 1.0. Sub-scores are capped at 1.0 even if matched weights sum higher, so over-weighting is forgiving — under-weighting starves the sub-score.

If a sub-score has three rules with weights 0.5 + 0.3 + 0.2 = 1.0, all three must match for the sub-score to reach 1.0. If only the 0.5 and 0.3 rules match, the sub-score is 0.8 (capped).

## Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Rule fires on irrelevant cases | False positives on grounded responses | Add a precondition check and abstain (`matched=True`) when the precondition is missing |
| Weights don't sum to ~1.0 in a sub-score | Sub-scores never reach high values | Audit the weight distribution within each sub-score |
| Flag predicate uses geometric mean | Safety failures masked by UX scores | Make the predicate non-compensatory: per-sub-score thresholds with `OR` |
| `check` function calls an LLM or HTTP | Non-deterministic verdicts | Move the LLM out of the check; use rules for pattern verification only |
| Empty citations on safety rules | Rule fails audit | Cite the source: academic paper, regulation, industry whitepaper |
| Rule set used outside its calibrated domain | Over-flags or under-flags badly | Build a domain-fit rule set; don't reuse the wrong one |

## Validating your rule set

Before deploying, run it on a labelled reference set. At minimum:

- 5-10 known-good responses (should pass)
- 5-10 known-bad responses (should fail with specific rules)
- 5-10 known-ambiguous responses (any verdict OK, but the audit trail should be human-readable)

Inspect the `audit_explanation` for each case. Read the rules that did not match — are they the right reasons? Read the rules that matched — are they the right reasons?

A rule set you can read out loud and defend is a rule set you can put in front of an auditor.

## See also

- [examples/custom_rules.py](../../examples/custom_rules.py) — runnable end-to-end legal contract review
- [src/groundlens/agents/customer_support.py](../../src/groundlens/agents/customer_support.py) — production customer-support RAG rule set, 7 rules, 3 sub-scores
- [src/groundlens/agents/routing.py](../../src/groundlens/agents/routing.py) — production routing agent rule set, 10 rules, 4 sub-scores
- [src/groundlens/agents/specialized.py](../../src/groundlens/agents/specialized.py) — production specialized agent rule set with strict predicate and external validators
- [Banking deployment guide](banking-deployment.md) — applying the 4-step recipe under SR 26-2 / EU AI Act constraints
