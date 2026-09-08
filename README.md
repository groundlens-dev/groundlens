<div align="center">

# GroundLens

![GroundLens](https://raw.githubusercontent.com/groundlens-dev/groundlens/main/docs/assets/Groundlens_02.png)

**The verification and evidence layer for AI.**

[![PyPI](https://img.shields.io/pypi/v/groundlens?color=1a4fd6)](https://pypi.org/project/groundlens/)
[![Python](https://img.shields.io/pypi/pyversions/groundlens)](https://pypi.org/project/groundlens/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Runtime dependencies](https://img.shields.io/badge/runtime%20deps-0-2c7a4b)](#python)
[![Rust](https://img.shields.io/badge/core-Rust-dea584)](crates)

[![CI](https://github.com/groundlens-dev/groundlens/actions/workflows/ci.yml/badge.svg)](https://github.com/groundlens-dev/groundlens/actions/workflows/ci.yml)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13390/badge)](https://www.bestpractices.dev/projects/13390)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/groundlens-dev/groundlens/badge)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)

[How it works](#how-it-works) · [Python](#python) · [Command line](#command-line) · [Determinism](#determinism-is-a-ci-job-not-a-sentence-in-a-readme) · [Crates](#crates) · [Status](#status)

</div>

<br>

Deterministic where possible, reproducible where required, explicit
provenance when not. Powered by the GLV engine.

A GroundLens **verifier produces evidence, never truth**. A **policy** turns
evidence into `PASS`, `REVIEW` or `FAIL`. The whole chain is sealed in a
**signed, hash-chained record** that anyone can check offline, and mapped
to the governance or regulatory controls your policy names.

```
answer + sources ──► claims ──► verifiers ──► evidence graph ──► policy ──► decision + controls
                                                                   │
                                                                   └──► signed, hash-chained evidence record
```

The engine measures. The policy interprets. The rules are yours. Those three
never mix, and that is the whole design.

## How it works

```
QUESTION    What is the invoice total?
SOURCE      ...the total amount due is 10,000 dollars, payable within 30 days...
ANSWER      The invoice total is 1,000 dollars, due in 30 days.
```

```python
from groundlens import verify

record = verify(answer, [("invoice.pdf#p1", source)], question=question, policy="eu_ai_act_high_risk_v1")
print(record.report())
```

```
FAIL  policy=eu_ai_act_high_risk_v1  record=rec_350455f44e60_4dbfea8eb79c
  c2   groundlens.numeric       contradicted  0.00  nearest in invoice.pdf#p1: '10,000 dollars'
```

Ten is not a hundred. An embedding sees the right answer and the wrong one
at 0.99 similarity; the numeric verifier compares quantities exactly, in
base units, and says which source span the number lost to. The policy turns
that evidence into a decision and maps it to Art. 15(1) and Art. 12(1) of
Regulation (EU) 2024/1689. The same engine reads `1.2 km` against `1200 m`,
`$37.35 billion` against a table cell `37,350` under "in millions of
dollars", and `212 °F` against `100 °C` as equal, with exact arithmetic.

## Python

```bash
pip install groundlens          # zero runtime dependencies, no network at any point
```

```python
from groundlens import verify, proofread, Policy, Record, Bundle, calibrate

record = verify("Revenue was €15M.", [("10k.pdf#p4", "Revenue was €10M.")])
record.decision        # 'FAIL'  (the policy decided; the verifier only produced evidence)
record.evidence[0]     # groundlens.numeric · contradicted · exact · nearest '€10M'
record.content_hash    # identical on every machine for the same input, policy and bundle
record.verify()        # recompute hashes and the Ed25519 signature, offline
```

`Policy` is YAML with a version and a hash; the hash goes into every record
it decides. Two policies over the same evidence can reach two decisions and
both are correct, which is what it means for the policy, not the engine, to
have an opinion. `Record.verify_chain()` checks a whole log.

The 3.x `proofread()` API is kept, same types and same numeral semantics,
and is tested against a golden file produced by groundlens 3.1 itself
(`python/tests/compat`). In this development build only the numeral channel
is scored; the lexical channel is the release gate of 4.0.0. Until then,
`pip install groundlens` gives you 3.1.

From source:

```bash
cd python && maturin build --release && pip install ../target/wheels/groundlens-*.whl
```

## Command line

```bash
groundlens verify --answer answer.txt --question question.txt \
  --source "invoice.pdf#p1=invoice.txt" --policy eu_ai_act_high_risk_v1 \
  --rules rules/es_banking_v1.yaml --locale en --log records.jsonl
groundlens record verify records.jsonl        # every hash, every link, every signature
groundlens report records.jsonl --out report  # report.md, report.json, records.jsonl, README-auditor.md
groundlens policy lint policies/eu_ai_act_high_risk_v1.yaml
```

Exit codes: `0` PASS, `1` FAIL, `2` error, `3` REVIEW. The Rust binary `glv`
exposes the same commands.

## Determinism is a CI job, not a sentence in a README

Functional determinism, declared per verifier and checked on every commit:

* same input, same bundle, same policy → **same classification**, on every OS and CPU;
* every score within a **declared tolerance** of the reference run;
* the **content hash** of the result is identical across platforms.

| class | example | guarantee |
|---|---|---|
| `exact` | numeric, rules | bit-identical, no floats decide anything |
| `reproducible` | NLI, lexical anchors, SGI, DGI | pinned ONNX hash + `cpu-f32` profile → scores within 1e-6 |
| `non_deterministic` | LLM-as-a-judge | recorded with model, prompt hash and settings; decides only if the policy says so |

A threshold compared with a drifting score is exactly where classifications
flip, so every threshold in a policy carries a **guard band**: a score inside
the band is `REVIEW` on every platform, and `policy lint` refuses a band
narrower than twice the verifier's tolerance.

`crates/gl-cli/tests/golden.rs` runs the invoice example under a Turkish
locale and a Pacific timezone on Linux x86_64, macOS arm64 and Windows, and
compares the record's `content_hash` with the committed golden value. A
change to that file has to explain itself in the commit.

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
| `gl-engine` | the one pipeline the CLI and every binding call |
| `gl-python` | `groundlens._engine`, the PyO3 extension |
| `gl-cli` | `glv` |

No crate in the engine depends on an HTTP or TLS library; a CI job fails
the build if one ever appears.

## Status

4.0 development. The contracts, the exact verifiers, the policy engine, the
signed records and the Python package are in place and tested end to end.
The lexical channel on ONNX, then NLI and semantic verifiers, then SGI and
DGI, calibration and the public benchmark follow, in that order. groundlens
3.x stays at tag `v3.1.0-final` and on PyPI until 4.0.0 ships.

<div align="center">

[groundlens.dev](https://groundlens.dev) · [Docs](https://docs.groundlens.dev) · [PyPI](https://pypi.org/project/groundlens/) · [Contributing](CONTRIBUTING.md) · Apache-2.0

<br>
Javier Marín, 2026 (javier@jmarin.info)
</div>
