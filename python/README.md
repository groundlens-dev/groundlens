# groundlens

**The verification and evidence layer for AI.** Powered by the GLV engine.

```python
from groundlens import verify

record = verify(
    answer="Revenue was €15M.",
    evidence=[("10k.pdf#p4", "Revenue was €10M.")],
)
record.decision          # 'FAIL'
record.reasons           # ['c2: groundlens.numeric contradicted: €15M not in sources; nearest 10000000 EUR ...']
record.content_hash      # identical on every machine for the same input, policy and bundle
```

A verifier produces evidence, never truth. A policy turns evidence into
`PASS`, `REVIEW` or `FAIL`. The whole chain is sealed in a signed,
hash-chained record that anyone can check offline with
`groundlens record verify`.

`pip install groundlens` pulls in nothing else: no numpy, no torch, no
network. Numeric verification, rules, policies, records and reports work
out of the box. Model-based verifiers (lexical, NLI, semantic, SGI, DGI)
need a bundle that you fetch once, on purpose, with `groundlens bundle pull`.

The 3.x `proofread()` API is kept. In this development build it scores the
numeral channel; the lexical channel returns with 4.0.0.
