# Measure and replay

Two questions come up once GroundLens is in production. **How many wrong
answers does our policy let through?** And **what would happen if we changed
it?** `measure` answers the first from a small sample your own team labels.
`replay` answers the second from your past traffic.

## Measure: what gets through

No verifier catches everything. The number that matters to the business is
the share of wrong answers among those that passed, because those reach
people without a review. GroundLens cannot know it alone: someone has to say
which answers were wrong. That someone is your team, on a small sample.

### 1. Draw the sample

```{code-block} bash
groundlens measure records/ --sample 50 --seed 7 > to-label.txt
```

The 50 record ids are drawn within each decision and risk class, in
proportion to their size and at least two per group. The list is shuffled and
carries no verdict, so whoever labels does not know what GroundLens decided.
Keep the seed: it goes into the report.

### 2. Label it

Look each answer up in your own logs by its record id, and mark it `wrong` or
`correct`. Save a CSV:

```{code-block} text
record_id,label
rec_3f2a9c11e0b4_1a2b3c4d5e6f,correct
rec_9d01b7e2c5aa_6f5e4d3c2b1a,wrong
```

### 3. Measure

```{code-block} bash
groundlens measure records/ --labels labels.csv --seed 7 \
  --review-minutes 4 --review-cost-per-hour 60 --error-cost 5000 \
  --out measurement.json
```

The report gives:

- **wrong among passed**: the share of wrong answers among those that passed,
  with a 95 % interval. If the interval is wider than ±5 %, the report says so:
  label more answers that passed.
- **wrong passed per 1,000 answers**: the same, per thousand answers of all
  kinds.
- the same **per risk class**;
- **cost**: review minutes and their cost, the expected cost of wrong answers
  that passed, and the cost per decision;
- **how it was computed**: the method, the strata and their weights, the seed.

The report is signed. `groundlens.measure.verify_signed` checks it.

### How the estimate works

Within each group of the sample (decision and risk class), the wrong rate is
estimated with the Agresti-Coull interval, which behaves well with few labels
and rates near zero. The groups that passed are combined by their share of
the passed answers.

If you have a score for **every** record that tends to be high on wrong
answers (for example a second, stronger model run offline over all traffic),
add it as a `prediction` column. The estimate then becomes
prediction-powered: the mean score over all records, corrected by the mean
error of the score on the labelled ones. A good score narrows the interval; a
useless one does not bias it.

## Replay: what a policy change would do

Before you tighten or relax a policy, run your past traffic under the new one:

```{code-block} bash
groundlens replay --traffic traffic.jsonl --records records/ --policy new-policy.yaml --out replay.json
```

`traffic.jsonl` holds one request per line, as you sent it: `answer`,
`passages` (each with `id`, `text` and `provenance`), and, when you have them,
`question`, `scope`, `risk_class` and the `record_id` of the record it
produced. Every request is checked again by the deterministic checks under the
new policy. The judge is not asked again when its evidence in the old record
answered exactly the same prompt; it is asked again (or left out) when the
prompt changed.

The report counts how many decisions would change, shows the transitions
(`PASS → REVIEW`: 30) and lists every changed record. Nothing is stored and no
record is written. The report is signed.
