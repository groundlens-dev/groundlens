# Writing a policy

A policy is where your organisation's judgement lives. This guide builds one
from the default, then tightens it. The full schema is in
[Policies](../concepts/policies.md).

## Start from a shipped policy

The fastest start is to copy `groundlens_default_v1` or
`eu_ai_act_high_risk_v1` and edit. The default is:

```{code-block} yaml
id: my_policy_v1
version: 1.0.0
verifiers:
  required: [groundlens.numeric]
  recommended: [groundlens.rules.*]
  optional: [groundlens.lexical, groundlens.nli]
  forbidden: [llm_judge.*]
determinism:
  minimum_to_decide: reproducible
decision:
  any_contradiction_from: [groundlens.numeric, groundlens.rules.*]
  unresolved_claims: REVIEW
  conflicts: REVIEW
  tolerate_unresolved_kinds: [word, statement]
```

## Decide what fails, what reviews, what passes

- Put the verifiers whose contradiction should **fail** the answer in
  `any_contradiction_from`. The exact verifiers (`groundlens.numeric`,
  `groundlens.rules.*`) belong here; a scored verifier usually does not.
- Send the rest to a human by leaving `unresolved_claims: REVIEW` and choosing
  which claim kinds you `tolerate_unresolved_kinds`.
- A scored verifier decides through `thresholds`, not contradictions.

## Add a scored channel with a guard band

If you install a bundle and want the lexical or entailment channel to influence
the decision, give it a threshold and a guard band:

```{code-block} yaml
thresholds:
  groundlens.lexical: { support_min: 0.60, guard_band: 0.02 }
  groundlens.nli:     { support_min: 0.85, guard_band: 0.02 }
```

The guard band must be at least twice the verifier's tolerance. A score inside
the band is REVIEW on every platform, so a small cross-platform drift can never
flip the decision. Do not put a threshold on an exact verifier; there is no
score to threshold, and `policy lint` rejects it.

## Map decisions to your framework

Add a `regulatory_mapping` so every record arrives tied to the control it
concerns. See [EU AI Act mapping](../concepts/eu-ai-act.md) for the shipped
example.

## Lint it, then use it

```{code-block} bash
groundlens policy lint my_policy_v1.yaml
```

```{code-block} python
from groundlens import verify, Policy
policy = Policy.from_yaml(open("my_policy_v1.yaml").read())
record = verify(answer, sources, policy=policy)
```

`policy lint` catches thresholds on exact verifiers, guard bands that are too
narrow, and unknown verifier ids before they ever reach a decision. To pick a
threshold from your own data rather than guessing, see
[Calibration](calibration.md).
