# Policies

The policy is the product. It is a short YAML document that says which
verifiers must run, what thresholds apply, and what happens to a claim nobody
could resolve. The engine holds no judgement of its own; the policy holds all
of it. The same evidence under two policies can produce two decisions, and both
are correct.

## Anatomy of a policy

```{code-block} yaml
id: eu_ai_act_high_risk_v1
version: 1.0.0
description: >
  Numbers must be exactly supported. A numeric contradiction fails the answer.
verifiers:
  required: [groundlens.numeric]
  recommended: [groundlens.rules.*]
  optional: [groundlens.nli, groundlens.lexical, sgi, dgi]
  forbidden: [llm_judge.*]
determinism:
  minimum_to_decide: reproducible
thresholds:
  groundlens.nli:     { support_min: 0.85, guard_band: 0.02 }
  groundlens.lexical: { support_min: 0.60, guard_band: 0.02 }
decision:
  any_contradiction_from: [groundlens.numeric, groundlens.rules.*]
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

### decision

- **any_contradiction_from** — a contradiction from any of these verifiers is a
  FAIL.
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

- **`groundlens_default_v1`** — numbers must be exactly supported; a numeric
  contradiction fails; anything unresolved goes to review; no generative
  verifier decides.
- **`eu_ai_act_high_risk_v1`** — the default, plus scored thresholds for the
  lexical and entailment channels and a mapping to Articles 15(1) and 12(1) of
  Regulation (EU) 2024/1689.

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
