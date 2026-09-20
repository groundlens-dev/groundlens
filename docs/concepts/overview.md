# How GroundLens works

GroundLens separates five things that most tools blur together. Keeping them
apart is what makes a decision auditable.

1. **Verifiers** produce evidence, never a verdict.
2. **Claims** are the atomic units a verifier is asked about.
3. **Evidence** is the structured output of a verifier for a claim.
4. **A policy** turns evidence into a decision. This is where the judgement lives.
5. **A record** seals the input, the evidence, the policy and the decision, signed and chained.

## The pipeline

```{code-block} text
answer + sources (+ question)
        │
        ▼
   claims                      atomic, checkable units extracted from the answer
        │
        ▼
   verifiers                   each produces evidence for the claims it can speak to
        │
        ▼
   evidence graph              every verifier's evidence for every claim, kept whole
        │
        ▼
   policy                      thresholds, required verifiers, what to do with the unresolved
        │
        ▼
   decision  +  record         PASS / REVIEW / FAIL, sealed and signed
```

The engine runs this once. The Python API, the command line and any other
binding call the same pipeline, so "verify an answer under a policy and seal
the record" has exactly one implementation.

## Why the separation matters

A verifier that also decided would bake one organisation's risk appetite into
the tool. By keeping the verifier to *measuring* and the policy to *deciding*,
the same evidence can be read strictly by one deployment and leniently by
another, and each can show precisely which rule it applied. When a regulator or
an internal auditor asks "why did this fail", the answer is not "the model said
so" but "the numeric verifier found a contradiction, and policy
`eu_ai_act_high_risk_v1` maps a numeric contradiction to FAIL under Article
15(1)".

## Answers and executions

The same contract covers two things:

- **An answer.** A model output and its sources. GroundLens extracts claims,
  verifies them, decides, and seals an [evidence record](records.md).
- **An execution.** A whole run of an agent or system: model calls, retrievals,
  tool requests and results, actions, human approvals. GroundLens records it as
  a hash-chained event log, gates it against an execution policy, and seals a
  [run record](runtime.md).

An answer verification is just a run with one claim, so nothing about the
answer pipeline changes when you move up to executions.
