# Quick start

This page verifies one answer end to end, in Python and on the command line,
and shows what comes back. It needs no bundle.

## Verify an answer in Python

```{code-block} python
from groundlens import verify

record = verify(
    "The invoice total is 1,000 dollars.",
    [("invoice.pdf#p1", "The total amount due is 10,000 dollars.")],
    question="What is the invoice total?",
    locale="en",
)

print(record.decision)     # FAIL
print(record.report())     # the reviewer's view: only what needs a look
```

`verify` reads the answer, extracts the claims it can check, runs each admitted
verifier, lets the policy turn the evidence into a decision, and seals the whole
thing in a signed record. Here the numeric verifier finds that the answer's
`1,000` is supported nowhere in the source and loses to `10,000`, so the default
policy fails the answer.

## Look at the evidence

A verifier never decides. It produces evidence; the record keeps all of it.

```{code-block} python
for e in record.evidence:
    print(e.verifier_id, e.result, round(e.score, 2), e.source_text)
```

## Seal it, and prove it later

```{code-block} python
record.verify()            # recompute every hash and the signature, offline
print(record.content_hash) # the same on any machine for the same input + policy
```

`record.verify()` raises if anything in the record was altered. It needs no key
material and no network: the public key travels inside the record.

## The same on the command line

```{code-block} bash
printf 'The invoice total is 1,000 dollars.' > answer.txt
printf 'The total amount due is 10,000 dollars.' > invoice.txt
printf 'What is the invoice total?' > question.txt

groundlens verify \
  --answer answer.txt \
  --source invoice.pdf#p1=invoice.txt \
  --question question.txt \
  --log records.jsonl

echo "exit code: $?"       # 1 = FAIL
groundlens record verify records.jsonl
```

## A different policy, a different decision

The engine has no opinion. Swap the policy and the same evidence can decide
differently, and both decisions are correct for their policy.

```{code-block} python
from groundlens import Policy

review_only = Policy.from_yaml("""
id: demo_review_only
version: 1.0.0
verifiers:
  required: [groundlens.numeric]
decision:
  any_contradiction_from: []
  unresolved_claims: REVIEW
  tolerate_unresolved_kinds: [word, statement]
""")

record = verify(
    "The invoice total is 1,000 dollars.",
    [("invoice.pdf#p1", "The total amount due is 10,000 dollars.")],
    policy=review_only,
)
print(record.decision)     # REVIEW
```

## Where to go next

- [Concepts](../concepts/overview.md) — what verifiers, evidence, policies and
  records actually mean.
- [Verify an answer](../guides/verify-an-answer.md) — the same task with
  paraphrases, units and multiple languages.
- [Writing policies](../guides/writing-policies.md) — build the rule that fits
  your deployment.
