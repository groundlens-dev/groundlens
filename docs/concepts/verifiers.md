# Verifiers

A verifier is a function that takes the verification input and produces
**evidence** about one or more claims. It never returns truth, and it never
decides. Every verifier, built-in or your own, follows the same contract:
`input → evidence`.

Each verifier declares a **determinism class** (see
[Determinism](determinism.md)) so a policy can refuse evidence that is not
reproducible enough to decide on.

## The built-in verifiers

| Id | Kind | What it checks | Determinism | Needs a bundle |
| --- | --- | --- | --- | --- |
| `groundlens.numeric` | exact | Numbers, currencies, percentages and physical units, compared as quantities in base units, with locale-aware parsing. | Exact | No |
| `groundlens.scope` | exact | Where each figure comes from: fails a figure found only in passages outside the request's scope (another company, contract or version). Runs when the request states a scope. See [Scope and provenance](scope.md). | Exact | No |
| `groundlens.rules` | symbolic | Your rule sets (YAML/JSON) run as checks. | Exact | No |
| `groundlens.lexical` | lexical/ML | Deprecated. Word-level grounding: each content word anchored to the source span that supports it, scored by a frozen multilingual encoder. | Reproducible | Yes (`base`) |
| `groundlens.nli` | ML | Deprecated. Entailment: each sentence-level statement checked against its sources by a three-way NLI classifier (entailment / neutral / contradiction). | Reproducible | Yes (a bundle carrying an entailment model) |
| `semantic.cosine` | statistical | Deprecated. Sentence similarity between each statement and its closest source passage, on the bundle's encoder. | Reproducible | Yes (`base`) |

```{admonition} The model channels are deprecated
:class: warning
`groundlens.lexical`, `groundlens.nli` and `semantic.cosine` run only when the
request names a bundle (`--bundle base`, `bundle="base"`), never by default,
and no shipped policy uses them. On real answers from annual reports,
contracts and a regulation they did not add value: the costly error is a real
figure attached to the wrong company, year or clause, and these channels check
that the words are present, not that they are bound to the right thing. They
leave the default build in the next release. The
[design page](../design/next.md) explains what replaces them.
```

## The numeric verifier in depth

`groundlens.numeric` is the workhorse and needs no model. It reads numbers the
way each language writes them and compares them as quantities, not strings:

- **Locales.** `10,000` (en) and `10.000` (de/es) are the same quantity; the
  `--locale` / `locale=` setting says which convention the documents use.
- **Scale words.** "ten thousand", "10K", "diez mil" and header-declared scales
  ("in millions of dollars") all normalise to base units.
- **Currencies, percentages, units.** `1,2 km` matches `1200 m`; `212 °F`
  matches `100 °C`; `37.35 billion` matches `37,350` under "in millions".
- **Two opt-in relaxations**, each noted in the receipt: `declared_precision`
  (accept a rounded figure) and `percent_as_fraction`.

A numeric mismatch is a **contradiction**, the strongest signal in the system,
and most policies map it straight to FAIL.

### Figures the answer computed

Answers show their work. "Expense fell from $77 million to $65 million, a
decline of $12 million, or 15.58 %." The decline and the percentage are in no
source, and they are right. The verifier recomputes them.

A figure that no source contains is checked against the other figures of the
same answer that the sources do support: their sum, their difference, their
ratio, and their percentage change. Each is computed as an exact fraction, with
no floating point, and compared with the figure the answer wrote at the
precision it wrote it. `15.58 %` has two decimals, so the exact value
`15.5844…` must round to `15.58`. A match is `supported`, with the note
`derived` and the formula in the rationale:

```{code-block} text
15.58% = |($65 million − $77 million) / $77 million| × 100 = 15.584415, rounded half_up
```

A figure that matches nothing stays a contradiction, so wrong arithmetic still
fails. A derived figure can feed the next one: the decline, then the decline as
a share of the first year.

Only the answer's own supported figures are operands, never two figures picked
from the sources. A table holds dozens of numbers, and some pair of them
matches almost any figure by chance.

The **rounding rule** says how a computed value may differ from the figure
written:

| rule | what it accepts | example, exact value `67.876…` |
|---|---|---|
| `half_up` (default) | round to nearest, ties away from zero | `67.9` |
| `half_even` | round to nearest, ties to the even digit | `67.9` |
| `within_last_digit` | rounded or truncated | `67.8` or `67.9` |

Set it with `rounding=` in Python or `--rounding` on the command line; turn
recomputation off with `derive=False` or `--no-derive`. A rounded match needs
at least two significant digits written, so `5 %` is never explained by
whatever happens to round to it; an exact match is accepted at any precision.

### What is not a wrong figure

- **Years.** A bare year that no source contains (`in 2015`, `(2011)`) is
  `unsupported` with the note `year_not_in_sources`, not a contradiction. A
  year is a label; its absence from a passage is not a wrong amount. A year is
  never an operand.
- **Formula constants.** The `100` of `× 100` and the divisor of an average,
  `(47 + 47) / 2`, are not claims.
- **A unit or scale stated on one side only.** A table cell says `5312` under a
  header the parser could not read, and the answer says `$5,312 million`. The
  same written number, with the unit or the scale on one side only, is
  `supported` with the note `unit_or_scale_on_one_side`, when it has at least
  three significant digits. Two different units (`EUR` and `USD`) or two
  different scales (`thousand` and `million`) are a different figure.

On 192 answers from a retrieval system over annual reports (FinQA questions,
labelled by hand or by exact comparison with the gold answer), these changes
moved the share of correct answers that failed from 90 % to 32 %. The share of
wrong answers flagged fell from 75 % to 38 %. Every one of those wrong answers
we looked at had correct arithmetic on figures that are in the sources; they
were wrong because the figures came from the wrong row, year or company, which
is not something a numeric check can see. The [scope check](scope.md) and a
judge are for that.

## Writing your own

A user-defined verifier is on the roadmap (5.2): a small interface, a declared
determinism class, recorded like any built-in, so your domain check joins the
same pipeline and lands in the same record. Adapters that run existing
detectors (for example Vectara HHEM or LettuceDetect) as verifiers are planned
alongside it.

See [Rules](../guides/rules.md) for the symbolic verifier you can use today
without writing code.
