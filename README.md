<!--
  BANNER GOES HERE.
  Drop the hero image in as the first line of this div, e.g.
      <img src="docs/assets/banner.png" alt="groundlens" width="820">
  Suggested subject: a proofread answer — most of the text untouched, two or
  three words underlined in red, a thin line from each to the span in the source
  it should have matched.
-->

<div align="center">

# groundlens

### A proofreader for RAG answers.

It marks the words your sources don't back, and shows you what each one should have matched.

[![PyPI](https://img.shields.io/pypi/v/groundlens?color=1a4fd6)](https://pypi.org/project/groundlens/)
[![Python](https://img.shields.io/pypi/pyversions/groundlens)](https://pypi.org/project/groundlens/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![CI](https://github.com/groundlens-dev/groundlens/actions/workflows/ci.yml/badge.svg)](https://github.com/groundlens-dev/groundlens/actions/workflows/ci.yml)
[![Determinism](https://github.com/groundlens-dev/groundlens/actions/workflows/determinism.yml/badge.svg)](https://github.com/groundlens-dev/groundlens/actions/workflows/determinism.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/groundlens-dev/groundlens/badge)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)
[![Runtime dependencies](https://img.shields.io/badge/runtime%20deps-0-2c7a4b)](#install)

[Install](#install) · [Quick start](#quick-start) · [How it works](#how-it-works) · [Why no threshold](#why-there-is-no-threshold) · [Scope](#scope) · [Retractions](RETRACTIONS.md) · [groundlens.dev](https://groundlens.dev)

</div>

---

## In twenty seconds

`groundlens` is an offline Python library. You give it a model's answer and the
passages it was supposed to write from. It gives you back the handful of words
those passages least support — each one printed next to the closest thing it
found in the source.

```
4.75%   support 0.00    nearest in policy.pdf#p3: '3.90%'
45      support 0.00    nearest in policy.pdf#p3: '30'
```

Marks in a margin. A proofreader doesn't grade your document — it flags the four
things worth a second look and leaves the judgement to you.

|  |  |
|---|---|
| **You give it** | an answer, and the passages behind it |
| **You get back** | the *k* weakest words, each with the source span it lost to |
| **It costs** | ~70 ms per answer on CPU. No training, no labels, no API call, no network |
| **It will not** | give you a pass, a fail, or a probability |

**What it is not.** Not a hallucination detector — it returns no verdict. Not an
eval framework like RAGAS or DeepEval — those score a *pipeline* over a dataset
before you ship, this inspects *one answer* at review time. Not a guardrail — it
blocks nothing and has no threshold to trip.

Two names, kept separate: **groundlens** is the library, **AnchorScore** is the
metric inside it.

---

## Install

```bash
pip install groundlens              # zero runtime dependencies. Not numpy, not torch
pip install "groundlens[encoder]"   # + the reference sentence encoder
pip install "groundlens[mcp]"       # + the MCP connector
```

The core install pulls **nothing**, and a CI job fails the build if that ever
changes. The previous version installed roughly two gigabytes of deep learning
stack before you had done anything.

---

## Quick start

```python
from groundlens import score, SentenceTransformerEncoder

answer = "The invoice total is 4.75% payable within 45 days."
sources = [("policy.pdf#p3", "The rate stated in the policy is 3.90% and the term is 30 days.")]

profile = score(answer, sources, encoder=SentenceTransformerEncoder(), k=2)

print(profile.report())
#  4.75%   support 0.00    nearest in policy.pdf#p3: '3.90%'
#  45      support 0.00    nearest in policy.pdf#p3: '30'
```

Every mark carries its receipt:

```python
for anchor in profile.weakest:
    anchor.text            # '4.75%'          the word in the answer
    anchor.span            # (21, 26)         where it sits
    anchor.kind            # 'numeral'        checked by arithmetic, not meaning
    anchor.support         # 0.0              absent from the sources
    anchor.evidence_id     # 'policy.pdf#p3'  which document to open
    anchor.evidence_text   # '3.90%'          what it should have matched
```

From the shell:

```bash
groundlens score --answer answer.txt --context policy.pdf#p3=policy.txt
```

---

## How it works

There are two kinds of content in an answer, and they need two different tests.

**Words are anchored by meaning.** A word's support is the highest cosine
similarity it reaches against any word of the sources, using a frozen
off-the-shelf encoder — the same kind your retrieval already uses.

**Numbers are anchored by arithmetic.** The numeral is parsed to a value with
formatting normalised — `10,000`, `10000`, `$10,000`, `10 000` and (under a
declared locale) `10.000` are one number — then checked against every value in
the sources. Support is exactly `1.0` or exactly `0.0`. Similarity is not allowed
to vote.

**And the score is the floor, not the average.** Every token-similarity metric
aggregates by the mean, and the mean is where single-token errors go to die.

### Ten is not a hundred

A retrieved document says the total due is **10,000 dollars**. The answer says
**1,000 dollars**. A human catches that instantly, without a finance degree.

Embedding similarity does not. Cosine between the right answer and the wrong one
is about 0.99 — the error dissolves into the vector the way a drop of ink
dissolves in a pool. An LLM judge does not either: it reads for plausibility, and
"the total is 1,000 dollars" is a perfectly plausible sentence about an invoice.
A trained span detector does not, because single-digit substitutions are rare in
its training labels.

Sentence encoders organise text by vocabulary, topic and structure. Never by
truth. A wrong number inside a correct sentence is, to a paraphrase-collapsing
encoder, very nearly a paraphrase.

On that invoice, the **mean** support of the wrong answer is 0.79 — which looks
fine. The **weakest anchor** is 0.00 — which is a mark in the margin.

---

## Why there is no threshold

We measured nine detectors across five public benchmarks — two published encoder
models, an NLI cross-encoder, an LLM judge, and this metric — at the operating
point production actually runs at: **false-positive rate at 95% hallucination
recall.**

| | best AUROC | FPR @ 95% recall |
|---|---:|---:|
| Trained span detector | 0.817 | 0.99 |
| Small trained fact-checker | 0.865 | 0.78 |
| LLM judge | 0.737 | 1.00 |
| NLI cross-encoder | 0.681 | 0.68 |
| **AnchorScore** | **0.857** | **0.70** |

Forty-five cells across the full grid. The best is **0.65**. A random detector
scores 0.95. One method ranks best of all by AUROC and flags **99% of correct
answers** at the operating point. Nobody is in the usable corner — **including us**.

So `score()` returns no `decision` field and the library ships no default cut. If
it did, someone would deploy it and be escalating two thirds of their clean
traffic within a week. That is not a limitation of this library; it is the
finding, and marks-not-verdicts is what you build once you take it seriously.

If you need a threshold, fit it on your own labelled traffic and read what it
costs you:

```python
from groundlens import calibrate

point = calibrate(labelled, target_recall=0.95)
print(point.threshold, point.fpr, point.fpr_ci95)   # read the fpr first
```

It refuses to run on fewer than 200 labelled examples, because below that a
95%-recall threshold is estimated from a handful of points.

---

## What reproduces, and what doesn't

**The numeral channel is exact.** Decimal comparison, fixed arithmetic context,
locale from an argument and never from `LC_ALL`. Byte-for-byte identical on any
machine — CI proves it on ten OS × Python combinations under
`PYTHONHASHSEED=random` and a Turkish locale.

**The lexical channel is float32 cosine** from a pinned encoder *revision* — not
a model name, because a silent re-upload would change every number you ever
published. It reproduces to 1e-6 across platforms and the ordering of the weakest
anchors is stable. It is **not** bit-identical between x86 and Apple Silicon, and
we do not claim it is.

`profile_sha256` covers the structure and the numeral supports exactly, and
rounds lexical supports to six decimals. Reproducing the hash reproduces the
finding. It does not reproduce the last bits of the arithmetic.

---

## Scope

It verifies **stated** values against a **retrieved** source. Like a human
proofreader, it can only check the document in front of it.

- It cannot verify computed values — "revenue tripled" against a source saying "revenue went from 5M to 15M".
- It cannot check reasoning. That belongs to entailment models.
- It inherits your retrieval. If the passage is wrong, so is the answer's grounding.
- Segmentation assumes space-delimited scripts, and warns rather than pretending when the text is largely CJK or Thai.

---

## Documentation

| If you want to | Go to |
|---|---|
| Understand the metric | [How it works](#how-it-works) |
| Know why there's no pass/fail | [Why there is no threshold](#why-there-is-no-threshold) |
| Use your own encoder | Implement the `Encoder` protocol — it has three members |
| Wire it into an agent | `pip install "groundlens[encoder,mcp]"`, then `python -m groundlens.mcp`. One tool: `find_unsupported_words` |
| Check it against a real model | `python scripts/verify_encoder.py` |
| See what was withdrawn | [RETRACTIONS.md](RETRACTIONS.md) |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Report a vulnerability | [SECURITY.md](SECURITY.md) |

---

## v3 is a rewrite, and previous numbers were withdrawn

Everything before v3 is gone: the geometry metrics, the rule engine, the agent
helpers, the framework integrations. 47,000 lines out, 2,200 in. Performance
figures that could not be regenerated from committed code have been retracted.

**[RETRACTIONS.md](RETRACTIONS.md) says exactly what was wrong and why.** Read it
before citing anything from this project. `git checkout v2.0.0` recovers the
entire previous tree.

---

<div align="center">

[groundlens.dev](https://groundlens.dev) · [PyPI](https://pypi.org/project/groundlens/) · [Retractions](RETRACTIONS.md) · [Contributing](CONTRIBUTING.md) · Apache-2.0

</div>
