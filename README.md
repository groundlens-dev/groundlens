# GroundLens

**The verification and evidence layer for AI.** Deterministic where possible, reproducible where required, explicit provenance when not. Powered by the GLV engine.

A policy engine over a pipeline of composable verifiers that emits a signed,
append-only evidence record mapped to regulation. Rust core, ONNX models,
one self-contained bundle, no network.

```
answer + sources ──► claims ──► verifiers ──► evidence graph ──► policy ──► decision + regulatory mapping
                                                                   │
                                                                   └──► signed, hash-chained evidence record
```

The engine measures. The policy interprets. The rules are yours. Those three
never mix, and that is the whole design.

## What "deterministic" means here

Functional determinism, declared per verifier and checked by CI:

* same input, same bundle, same policy → **same classification**, on every OS and CPU;
* every score within a **declared tolerance** of the reference run;
* the **content hash** of the result is identical across platforms.

Three classes, carried on every piece of evidence and in every record:

| class | example | guarantee |
|---|---|---|
| `exact` | numeric, rules | bit-identical, no floats decide anything |
| `reproducible` | NLI, lexical anchors, SGI, DGI | pinned ONNX hash + `cpu-f32` profile → scores within 1e-6 |
| `non_deterministic` | LLM-as-a-judge | recorded with model, prompt hash and settings; never decides unless the policy says so |

A threshold compared with a drifting score is exactly where classifications
flip, so every threshold in a policy carries a **guard band**: a score inside
the band is `REVIEW` on every platform. `glv policy lint` refuses a band
narrower than twice the verifier's tolerance.

## Python

```bash
cd python && maturin build --release && pip install ../target/wheels/groundlens-*.whl
```

```python
from groundlens import verify, proofread, Policy, Record, Bundle, calibrate

record = verify("Revenue was €15M.", [("10k.pdf#p4", "Revenue was €10M.")])
record.decision        # 'FAIL'  (the policy decided; the verifier only produced evidence)
record.evidence[0]     # groundlens.numeric · contradicted · exact · nearest '€10M'
record.verify()        # recompute hashes and the Ed25519 signature, offline
```

`pip install groundlens` pulls in nothing else and never opens a network
connection. The 3.x `proofread()` API is kept and its numeral channel is
checked against a golden file produced by groundlens 3.1 itself
(`python/tests/compat`). The lexical channel is the release gate of 4.0.0.

## Try it

```bash
cargo build --release
./target/release/glv policy lint policies/eu_ai_act_high_risk_v1.yaml
./target/release/glv verify \
  --answer   examples/invoice/answer.txt \
  --question examples/invoice/question.txt \
  --source   "invoice.pdf#p1=examples/invoice/invoice.txt" \
  --policy   policies/eu_ai_act_high_risk_v1.yaml \
  --rules    rules/es_banking_v1.yaml \
  --locale en --log records.jsonl
./target/release/glv record verify records.jsonl
```

The example answer says `1,000 dollars`; the source says `10,000 dollars`.
The numeric verifier contradicts claim `c2` with a receipt pointing at the
source span, the policy turns that into `FAIL`, and the record maps it to
Art. 15(1) and Art. 12(1) of Regulation (EU) 2024/1689. The same answer also
says `1.2 km` against a source saying `1200 m`, and `$37.35 billion` against
a table cell reading `37,350` under a header "in millions of dollars". Both
are `supported`, exactly.

## Crates

| crate | what it owns |
|---|---|
| `gl-core` | `Claim`, `Evidence`, the `Verifier` trait, `EvidenceGraph`, determinism classes, canonical JSON + SHA-256 |
| `gl-text` | NFKC normalisation, thin-space group separators, word segmentation, stopwords (en, es) |
| `gl-numeric` | numerals with locale, scale words (short and long scale), currencies, percent, physical units with exact rational conversion, header-declared scales |
| `gl-verifiers` | claim extractor, `groundlens.numeric` (exact), `groundlens.rules` (symbolic) |
| `gl-policy` | policy schema (YAML), lint, evaluation, guard bands, regulatory mapping |
| `gl-record` | evidence record, hash chain, Ed25519 signatures, JSON Lines log |
| `gl-bundle` | bundle manifest, artefact hashing, offline-only flag |
| `gl-onnx` | `Encoder` and `EntailmentModel` traits, SGI and DGI formulas; ONNX Runtime behind the `runtime` feature |
| `gl-cli` | `glv` |

## Determinism is a CI job, not a sentence in a README

`crates/gl-cli/tests/golden.rs` runs the invoice example under a Turkish
locale and a Pacific timezone on Linux, macOS (arm64) and Windows, and
compares the record's `content_hash` with the committed golden value. A
change to that file has to explain itself in the commit.

## Status

0.1.0 is the contract plus the two exact verifiers, end to end. The ONNX
verifiers, the Python binding and the WASM build are milestones M2 to M4 in
the specification. groundlens 3.x (Python) remains the reference
implementation of the lexical channel until M2 reproduces its numbers.

Apache-2.0. Javier Marín, 2026.
