# Determinism

Every verifier declares a **determinism class**, and a policy can refuse to
decide on evidence weaker than a class it names.

## The classes

| Class | Meaning | Verifiers |
| --- | --- | --- |
| `exact` | No floating point. The same input gives bit-identical output, everywhere, always. | `groundlens.numeric`, `groundlens.scope`, `groundlens.intent`, `groundlens.rules.*` |
| `reproducible` | The same result within a declared tolerance across platforms. | none built in; kept so records from 5.x, whose model channels were in this class, still read |
| `non_deterministic` | Not guaranteed to repeat. Recorded in full: the model the provider returned, the hash of the prompt and of the reply. | `llm_judge.<adapter>`, the judge |

A policy's `determinism.minimum_to_decide` (`exact`, `reproducible` or `any`)
says which classes may drive the decision. The shipped policies forbid the
judge; a policy that wants one says how its labels count in `judge:`. See
[Use a judge](../guides/use-a-judge.md).

## What this buys the record

Every built-in check is exact, so the record's `content_hash` is the same for
the same input and policy on any machine. That is what lets an auditor
recompute a decision independently and get the same answer. CI checks it on
Linux, macOS and Windows against a committed hash, in a hostile locale and
time zone.

The judge is the one exception, and the record says so: its evidence carries
the class `non_deterministic`, the model and the prompt hash.
