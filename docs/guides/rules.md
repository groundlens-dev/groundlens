# Writing rules

The rules verifier (`groundlens.rules`) runs logic **your** organisation writes,
as a first-class verifier with exact determinism. A rule looks at claims (their
kind, attributes and text) and at the answer, and emits evidence. It never looks
at other verifiers' evidence — composing evidence is the [policy's](../concepts/policies.md)
job. Keeping the two apart is what lets a rule set be versioned, hashed and
reviewed on its own.

## A rule set

A rule set is YAML (or JSON) with an id, a version and a list of rules.

```{code-block} yaml
id: es_banking_v1
version: 1.0.0
rules:
  - id: no_apr_without_percent
    description: "An APR must be stated as a percentage"
    scope: { claim_kind: numeric }
    when: { text_matches: "(?i)\\bTAE\\b|\\bAPR\\b" }
    unless: { attribute: { dimension: percent } }
    emit: contradicted
  - id: currency_claims_need_currency
    scope: { claim_kind: numeric, attribute: { dimension: dimensionless } }
    when: { answer_matches: "(?i)euros?|€|dólares|\\$" }
    emit: unsupported
```

### Fields

- **scope** — which claims the rule looks at: `claim_kind` (`numeric`, `word`,
  `statement`) and/or `attribute` key/value pairs (for example a numeric claim's
  `dimension`).
- **when** — the condition that fires the rule: `text_matches` (regex over the
  claim text), `answer_matches` (regex over the whole answer), `source_matches`
  (regex that must match some source), and/or `attribute` pairs.
- **unless** — the same shape as `when`; if it holds, the rule does not fire.
- **emit** — the evidence to produce when the rule fires: `contradicted`,
  `unsupported`, `supported`.

Conditions use standard regular expressions, so `(?i)` for case-insensitive and
`\b` for word boundaries work as expected.

## Using rules

```{code-block} python
from groundlens import verify

record = verify(
    answer, sources,
    rules=["es_banking_v1.yaml"],       # paths, or dicts, repeatable
    policy="eu_ai_act_high_risk_v1",
)
```

```{code-block} bash
groundlens verify --answer a.txt --source s=s.txt --rules es_banking_v1.yaml
```

For a policy to let rules **fail** an answer, list `groundlens.rules.*` in the
policy's `any_contradiction_from`. The shipped policies already do.
