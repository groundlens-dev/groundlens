# groundlens

**Shows you which words in an answer your sources don't support — and what each one lost to.**

```
4.75%   support 0.00    nearest in policy.pdf#p3: '3.90%'
45      support 0.00    nearest in policy.pdf#p3: '30'
```

That is the output. Not a score you have to interpret, not a verdict you have to
trust — the two or three words a reviewer should look at, each printed next to
the closest thing in the source. Thirty seconds instead of five minutes.

```bash
pip install "groundlens[encoder]"
```

```python
from groundlens import score, SentenceTransformerEncoder

profile = score(
    answer,
    [("policy.pdf#p3", passage)],
    encoder=SentenceTransformerEncoder(),
)
print(profile.report())
```

---

## Ten is not a hundred

A retrieved document says the total due is **10,000 dollars**. The answer says
**1,000 dollars**. A human catches that instantly, without a finance degree.

Embedding similarity does not. Cosine between the correct answer and the wrong
one is about 0.99 — the error dissolves into the vector the way a drop of ink
dissolves in a pool. An LLM judge does not either: it reads for plausibility,
and "the total is 1,000 dollars" is a perfectly plausible sentence about an
invoice. A span detector trained on labelled hallucinations does not, because
single-digit substitutions are rare in its training labels.

Sentence encoders organise text by vocabulary, topic and structure. Never by
truth. A wrong number inside a correct sentence is, to a paraphrase-collapsing
encoder, very nearly a paraphrase.

So groundlens uses two different tests for two different kinds of content.

**Words are anchored by meaning.** A word's support is the highest cosine
similarity it reaches against any word of the sources.

**Numbers are anchored by arithmetic.** The numeral is parsed to a value with
formatting normalised — `10,000`, `10000`, `$10,000`, `10 000` and `10.000` are
one number — and checked against every value in the sources. Support is exactly
`1.0` or exactly `0.0`. Similarity is not allowed to vote.

**And the score is the floor, not the average.** Every token-similarity metric
aggregates by the mean, and the mean is where single-token errors go to die. On
the invoice above, mean support of the wrong answer is 0.79, which looks fine.
The weakest anchor is 0.00, which is an alarm.

---

## There is no threshold, and that is deliberate

We measured nine detectors across five public benchmarks — two published encoder
models, an NLI cross-encoder, an LLM judge, and this metric — at the operating
point production actually runs at: **false-positive rate at 95% hallucination
recall.**

Forty-five cells. The best is **0.65**. A random detector scores 0.95.

One method ranks best of all on RAGTruth by AUROC — 0.817 — and flags **99% of
correct answers** at 95% recall. The LLM judge is at 1.00 on all five, at fifty
times the latency and a per-call bill. Nobody is in the usable corner. Including us.

So `score()` returns no `decision` field and the library ships no default cut.
If we shipped one, someone would deploy it, and they would be escalating two
thirds of their clean traffic within a week. If you need a threshold, fit it on
your own labelled traffic and read what it costs you:

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
machine. CI proves it on ten OS × Python combinations under `PYTHONHASHSEED=random`
and a Turkish locale.

**The lexical channel is float32 cosine** from a pinned encoder *revision* — not
a model name, because a silent re-upload would change every number you ever
published. It reproduces to 1e-6 across platforms and the ordering of the
weakest anchors is stable. It is **not** bit-identical between x86 and Apple
Silicon, and we do not claim it is.

`profile_sha256` covers the structure and the numeral supports exactly, and
rounds lexical supports to six decimals. Reproducing the hash reproduces the
finding. It does not reproduce the last bits of the arithmetic.

---

## Scope

It verifies **stated** values against a **retrieved** source. Like a human
reviewer, it can only check the document in front of it.

It cannot verify computed values — "revenue tripled" against a source saying
"revenue went from 5M to 15M". It cannot check reasoning; that is entailment
territory. It inherits your retrieval: if the passage is wrong, so is the
answer's grounding. Segmentation assumes space-delimited scripts and warns when
the text is largely CJK or Thai rather than pretending.

No training. No labels. No API call. No network. `pip install groundlens` has
**zero runtime dependencies** — a CI job fails the build if that ever changes.

---

## Also

- **CLI** — `groundlens score --answer answer.txt --context policy.pdf#p3=policy.txt`
- **MCP** — one tool, `find_unsupported_words`. `pip install "groundlens[encoder,mcp]"`, then `python -m groundlens.mcp`
- **Your own encoder** — implement the `Encoder` protocol; it has three members

---

## v3 is a rewrite, and previous numbers were withdrawn

Everything before v3 is gone: the geometry metrics, the rule engine, the agent
helpers, the framework integrations, 47,000 lines of it. Published performance
figures that could not be regenerated from committed code have been retracted.

**[RETRACTIONS.md](RETRACTIONS.md) says exactly what was wrong and why.** Read
it before citing anything from this project. `git checkout v2.0.0` recovers the
entire old tree.

Apache-2.0.
