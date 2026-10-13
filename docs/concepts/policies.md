# Policies

The policy is the product. It is a short YAML document that says which
verifiers must run, what thresholds apply, and what happens to a claim nobody
could resolve. The engine holds no judgement of its own; the policy holds all
of it. The same evidence under two policies can produce two decisions, and both
are correct.

Every key is checked. A key the schema does not know is an error, not a
silent no-op, so a typo such as `rouding:` cannot switch a rule off without
anyone noticing.

## Anatomy of a policy

```{code-block} yaml
id: eu_ai_act_high_risk_v1
version: 1.3.0
description: >
  Numbers must be exactly supported. A numeric contradiction fails the answer,
  and so does a figure taken from outside the request's scope.
verifiers:
  required: [groundlens.numeric]
  recommended: [groundlens.scope, groundlens.intent, groundlens.rules.*]
  forbidden: [llm_judge.*]
determinism:
  minimum_to_decide: reproducible
decision:
  any_contradiction_from: [groundlens.numeric, groundlens.scope, groundlens.rules.*]
  unsupported_from: [groundlens.scope, groundlens.intent]
  unresolved_claims: REVIEW
  conflicts: REVIEW
  tolerate_unresolved_kinds: [word, statement]
regulatory_mapping:
  - framework: EU-AI-Act-2024/1689
    article: "Art. 15(1)"
    control: accuracy-of-outputs
    triggered_by: [FAIL, REVIEW]
```

### id, version and description

`id` and `version` name the policy in every record it decides. `description`
says in plain words what the policy enforces.

### extends

A policy can be written on top of a shipped one and say only what differs:

```{code-block} yaml
id: credit_desk
version: 3.0.0
extends: eu_ai_act_high_risk_v1
rounding: half_even
scope:
  required: [entity]
```

Maps merge key by key: the `decision` keys you do not write come from the
baseline. Lists and single values replace: a `required` list you write is the
whole list. A policy that extends another must set its own `id` and
`version`, so its records are never mistaken for the baseline's. `extends`
names a shipped policy (`groundlens_default_v1` or `eu_ai_act_high_risk_v1`);
it does not read other files, so the same policy text always resolves to the
same policy.

The policy that decides is the **resolved** one: the baseline with your
changes merged in and every default written out. Its hash is the one in every
record. `groundlens policy show my-policy.yaml --resolved` prints it, headed
by that hash.

### pass_means

One sentence on what `PASS` means for your application, for example
`"may be shown to the analyst as an evidence summary"`. A decision of the
verifier is not a decision to publish; this says which one it is. It travels
in the policy and in the decision of every record.

### locale and rounding

`locale` says how your documents write numbers (`es-ES`, `en`, `de`...).
`rounding` says how a figure the answer computed may differ from the exact
result at the precision written: `half_up`, `half_even` or
`within_last_digit`. When the policy sets either one, **the policy wins** over
the request: a `locale` or `rounding` passed with a request is ignored. The
same policy hash then always means the same reading of the numbers.

### scope

```{code-block} yaml
scope:
  required: [entity]
  missing_scope: REVIEW
```

`required` lists the [scope](scope.md) keys every request must carry. A
request without one of them goes to `missing_scope`, which is `REVIEW` by
default and may be `FAIL`, never `PASS`. The reason (`missing_scope: the
request does not say its entity`) is in the record.

### risk_classes

```{code-block} yaml
risk_classes:
  default: routine
  routine: [lookup]
  mandatory_review: [recommendation]
```

A risk class sorts requests by what an error would cost. A request names its
class (`risk_class="recommendation"`, `--risk-class recommendation`); a
request that names none gets `default`. A class listed under
`mandatory_review` goes to `REVIEW` even when every check passes. A class the
policy does not list is an error, so a typo cannot route a request around
review. The class is written into the record.

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

## When something goes wrong

Nothing that went wrong can pass:

| situation | decision |
| --- | --- |
| a required verifier did not run | REVIEW |
| a verifier could not run at all | REVIEW (ignored if the policy forbids that verifier) |
| a verifier errored on a claim that needs a verdict | REVIEW |
| a required scope key is missing | `missing_scope` (REVIEW by default) |
| the request's risk class requires review | REVIEW |
| the request names a risk class the policy does not list | error, no record |

The final decision is the worst of all of these and of every claim.

## The shipped policies

- **`groundlens_default_v1`** (version 1.3.0) — numbers must be exactly
  supported; a numeric contradiction fails; a figure taken from outside the
  request's [scope](scope.md) fails, and one from a passage without provenance
  goes to review; a figure that is not the kind or unit the question asked for
  goes to review; anything unresolved goes to review; no model is needed and
  no generative verifier decides.
- **`eu_ai_act_high_risk_v1`** (version 1.3.0) — the same checks, plus a
  mapping to Articles 15(1), 14(4)(a) and 12(1) of Regulation (EU) 2024/1689.

Version 1.2.0 of both removes the model channels (`groundlens.lexical`,
`groundlens.nli`, `semantic.cosine`) and their thresholds. Decisions on
requests without a bundle are unchanged; only the policy version and hash in
the record differ. Version 1.3.0 adds the intent check, which sends to review
an answer whose figure is not the kind or the unit the question asked for.

## Using and checking a policy

```{code-block} python
from groundlens import verify, Policy

record = verify(answer, sources, policy="eu_ai_act_high_risk_v1")

custom = Policy.from_yaml(open("my-policy.yaml").read())
record = verify(answer, sources, policy=custom)
```

```{code-block} bash
groundlens policy lint my-policy.yaml
groundlens policy show my-policy.yaml --resolved
```

`policy lint` rejects unknown keys, unknown rounding rules, a `missing_scope`
of `PASS`, a risk class listed twice, thresholds on exact verifiers (a threshold on an exact
score is meaningless), guard bands narrower than twice the verifier tolerance,
and unknown verifier ids. See [Writing policies](../guides/writing-policies.md)
for a step-by-step build and {class}`groundlens.Policy` for the API.
