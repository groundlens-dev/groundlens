# Verifiers

A verifier is a function that takes the verification input and produces
**evidence** about one or more claims. It never returns truth, and it never
decides. Every verifier, built-in or your own, follows the same contract:
`input → evidence`.

Each verifier declares a **determinism class** (see
[Determinism](determinism.md)) so a policy can refuse evidence that is not
reproducible enough to decide on.

## The built-in verifiers

| Id | Kind | What it checks | Determinism | Needs a model |
| --- | --- | --- | --- | --- |
| `groundlens.numeric` | exact | Numbers, currencies, percentages and physical units, compared as quantities in base units, with locale-aware parsing. | Exact | No |
| `groundlens.scope` | exact | Where each figure comes from: fails a figure found only in passages outside the request's scope (another company, contract or version). Runs when the request states a scope. See [Scope and provenance](scope.md). | Exact | No |
| `groundlens.intent` | symbolic | Whether the answer's figure is the kind and unit the question asked for: a percentage when a percentage was asked, an amount in euros when euros were asked. Runs when the request has a question. | Exact | No |
| `groundlens.rules` | symbolic | Your rule sets (YAML/JSON) run as checks. | Exact | No |
| `llm_judge.<adapter>` | generative | The model you already use, asked a fixed question per sentence: supported, unsupported, contradicted or uncertain. Can only escalate. See [Use a judge](../guides/use-a-judge.md). | Non-deterministic | No (your own client) |

## The numeric verifier in depth

`groundlens.numeric` is the workhorse and needs no model. It reads numbers the
way each language writes them and compares them as quantities, not strings:

- **Locales.** `10,000` (en) and `10.000` (de/es) are the same quantity; the
  `--locale` / `locale=` setting says which convention the documents use.
- **Scale words.** "ten thousand", "10K", "diez mil" and header-declared scales
  ("in millions of dollars") all normalise to base units.
- **Currencies, percentages, units.** `1,2 km` matches `1200 m`; `212 °F`
  matches `100 °C`; `37.35 billion` matches `37,350` under "in millions".
- **Single digits.** `$2 million`, `5 %` and `7 days` are figures. A bare
  single digit is not: it is usually a list or page number.
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
fails. That holds even when no source states a figure of that kind: in "from
€38.0 million to €41.2 million, up 12 %", the passages contain no percentage,
but the answer's two amounts give 8.42 %, so `12 %` is contradicted, with the
note `recomputation_mismatch`. A derived figure can feed the next one: the
decline, then the decline as a share of the first year.

A figure that no source contains and that the answer gives nothing to
recompute from ("revenue grew 12 %" on its own) is `unsupported`, and the
shipped policies send it to review: nothing contradicts it, and nothing
supports it.

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

## The intent check

An answer can quote a real figure that is the wrong kind of answer. Asked
"what portion of the obligations is related to equity?", a model replies
"$1,246 million". The figure is in the source, so the numeric and scope checks
pass it. The question asked for a portion.

`groundlens.intent` reads the question and the answer's last figure that is not
a year (answers that show their work end with the result):

| the question says | it asks for | the figure must be |
|---|---|---|
| "percentage", "portion", "proportion", "ratio", "growth rate", "porcentaje" | a percentage | a percentage or a bare number (`22.97 %`, `0.23`) |
| "how many", "number of", "cuántos" | a count | not a percentage |
| "how much", "in millions", "total", "amount", "cuánto", "importe" | an amount | not a percentage |
| "in euros", "in millions of dollars", "en kilómetros" | that unit | in that unit, not a percentage unless one was asked (`unit_mismatch`), and with a unit (`unit_missing`) |

A figure of the kind asked is `supported`. One that is not is `unsupported`
with the note `intent_mismatch`, `unit_mismatch` or `unit_missing`, and the
shipped policies send it to review, never to fail: the check reads words, so it
can be wrong. A question with none of these signals, or an answer with no
figure, gets no evidence from it.

On 192 labelled answers over annual reports it flagged 10 answers: 8 were
wrong, and the 2 correct ones answered a "percentage return" question with the
dollar value of an investment.

## Writing your own

Today a domain check joins the pipeline as a rule set: see
[Rules](../guides/rules.md), the symbolic verifier you can use without writing
code. A check that reads meaning goes through the [judge](../guides/use-a-judge.md),
with your own model. Custom checks written in Python, with a declared
determinism class and the hash of their source in the record, are part of the
design in [What changes next](../design/next.md).
