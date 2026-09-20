# EU AI Act mapping

GroundLens does not claim to make a system compliant. It gives you the two
things a high-risk AI deployment under Regulation (EU) 2024/1689 has to be able
to produce: evidence that outputs were checked, and a durable, tamper-evident
record of that checking. A policy ties each decision to the article it concerns,
and the mapping travels inside every record.

## The shipped mapping

`eu_ai_act_high_risk_v1` is written for a retrieval-augmented assistant whose
outputs feed a decision listed in Annex III. Its `regulatory_mapping` connects
outcomes to three articles:

| Article | Control | Triggered by |
| --- | --- | --- |
| **Art. 15(1)** — accuracy and robustness | accuracy-of-outputs | FAIL |
| **Art. 14(4)(a)** — human oversight | human-oversight-review-queue | REVIEW |
| **Art. 12(1)** — record keeping | automatic-record-keeping | PASS, REVIEW, FAIL |

Read as a workflow: a checkable contradiction **fails** the output (accuracy,
Art. 15); anything a deterministic verifier cannot resolve goes to a human
**review** queue (oversight, Art. 14); and **every** outcome is written to a
signed, chained log (record keeping, Art. 12).

## Why the mapping lives in the policy, not the engine

What a decision means for compliance is a judgement your organisation makes, and
it can change without changing the engine. Keeping the mapping in the policy —
and hashing the policy into every record — means each record states which
mapping was in force when the decision was taken. When the rule changes, old
records still show the rule they were decided under.

## What you get for an audit

- A decision tied to a named article and control, inside the record.
- A signed, hash-chained log that satisfies the record-keeping requirement on
  its own terms: it is verifiable offline by anyone with the file.
- A reproducible content hash, so a decision can be recomputed independently.

To assemble this into a package for a conformity file or a procurement review,
see [Evidence for auditors](../guides/evidence-for-auditors.md).

```{admonition} Not legal advice
This mapping is a starting point that reflects one reasonable reading of the
Regulation. Your legal and compliance teams own the interpretation for your
deployment; the policy is designed to be edited to match it.
```
