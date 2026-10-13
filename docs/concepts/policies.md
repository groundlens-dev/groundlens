# Policies

The policy is the product. It is a short YAML document that says which
verifiers must run, what thresholds apply, and what happens to a claim nobody
could resolve. The engine holds no judgement of its own; the policy holds all
of it. The same evidence under two policies can produce two decisions, and both
are correct.

## Anatomy of a policy

```{code-block} yaml
id: eu_ai_act_high_risk_v1
version: 1.2.0
description: >
  Numbers must be exactly supported. A numeric contradiction fails the answer,
  and so does a figure taken from outside the request's scope.
verifiers:
  required: [groundlens.numeric]
  recommended: [groundlens.scope, groundlens.rules.*]
  forbidden: [llm_judge.*]
determinism:
  minimum_to_decide: reproducible
decision:
  any_contradiction_from: [groundlens.numeric, groundlens.scope, groundlens.rules.*]
  unsupported_from: [groundlens.scope]
  unresolved_claims: REVIEW
  conflicts: REVIEW
  tolerate_unresolved_kinds: [word, statement]
regulatory_mapping:
  - framework: EU-AI-Act-2024/1689
    article: "Art. 15(1)"
    control: accuracy-of-outputs
    triggered_by: [FAIL, REVIEW]
```

### verifiers

Five lists, each a set of verifier ids (globs like `groundlens.rules.*` are
allowed):

- **required** — must run, or the verification cannot decide.
- **recommended** — run if available.
- **optional** — run if available; their absence is fine.
- **fallback** — used only when nothing better resolved a claim.
- **forbidden** — must not run. A conservative deployment forbids
  `llm_judge.*`; a research deployment allows it.

### determinism

`minimum_to_decide` is the weakest [determinism class](determinism.md) whose
evidence the policy will act on: `exact`, `reproducible`, or `any`. Evidence
from a verifier below this class is recorded but does not drive the decision.

### thresholds

For a scored verifier, `support_min` is the score below which a claim is not
considered supported, and `guard_band` is a band around it. A score **inside**
the guard band is REVIEW on every platform, so a small cross-platform score
drift can never flip a PASS into a FAIL. `policy lint` requires the guard band
to be at least twice the verifier's declared tolerance.

No shipped policy sets thresholds: the checks in the default path are exact,
and exact verifiers have no score to threshold. Thresholds apply to the
deprecated model channels, if you still run them with a bundle:

```{code-block} yaml
thresholds:
  groundlens.nli:     { support_min: 0.85, guard_band: 0.02 }
  groundlens.lexical: { support_min: 0.60, guard_band: 0.02 }
```

### decision

- **any_contradiction_from** — a contradiction from any of these verifiers is a
  FAIL.
- **unsupported_from** — an `unsupported` from any of these verifiers sends the
  claim to REVIEW: the verifier could not establish what it checks, for example
  a figure whose passage does not state its provenance. Optional; when it is
  empty it is left out of the policy hash.
- **unresolved_claims** — what to do with a claim no admitted verifier could
  resolve (usually REVIEW).
- **conflicts** — what to do when verifiers disagree about a claim.
- **tolerate_unresolved_kinds** — claim kinds that may go unresolved without
  triggering `unresolved_claims`. For example, tolerating `word` and
  `statement` means the decision rests on the exact verifiers unless a scored
  channel is present.

### regulatory_mapping

Zero or more controls, each with a framework, an article, a control name and
the decisions that trigger it. The mapping travels inside the record, so a
decision arrives already tied to the rule it concerns. See
[EU AI Act mapping](eu-ai-act.md).

## The shipped policies

- **`groundlens_default_v1`** (version 1.2.0) — numbers must be exactly
  supported; a numeric contradiction fails; a figure taken from outside the
  request's [scope](scope.md) fails, and one from a passage without provenance
  goes to review; anything unresolved goes to review; no model is needed and no
  generative verifier decides.
- **`eu_ai_act_high_risk_v1`** (version 1.2.0) — the same checks, plus a
  mapping to Articles 15(1), 14(4)(a) and 12(1) of Regulation (EU) 2024/1689.

Version 1.2.0 of both removes the model channels (`groundlens.lexical`,
`groundlens.nli`, `semantic.cosine`) and their thresholds. Decisions on
requests without a bundle are unchanged; only the policy version and hash in
the record differ.

## Using and checking a policy

```{code-block} python
from groundlens import verify, Policy

record = verify(answer, sources, policy="eu_ai_act_high_risk_v1")

custom = Policy.from_yaml(open("my-policy.yaml").read())
record = verify(answer, sources, policy=custom)
```

```{code-block} bash
groundlens policy lint my-policy.yaml
```

`policy lint` rejects thresholds on exact verifiers (a threshold on an exact
score is meaningless), guard bands narrower than twice the verifier tolerance,
and unknown verifier ids. See [Writing policies](../guides/writing-policies.md)
for a step-by-step build and {class}`groundlens.Policy` for the API.
