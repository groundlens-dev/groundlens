# Benchmark fallback data

## Label convention in this file - read this before you load it

> **In `confabulation_benchmark.csv`, `label=1` is the GROUNDED response and
> `label=0` is the confabulation.** `benchmarks/confabulation_benchmark.py`
> uses the same convention.
>
> **The library and the documentation use the opposite one.**
> `groundlens.fit_thresholds()`, the README's calibration section and the pages
> under `docs/` all take `1 = ungrounded`.
>
> Both conventions are internally self-consistent, so nothing raises. Feed this
> CSV straight into `fit_thresholds()` and it silently fits inverted
> thresholds and reports a plausible-looking number. Flip the column first.
>
> This is an open inconsistency in the repository, not a documentation slip.
> Which convention becomes canonical is a decision for a human; until it is
> made, check the polarity of every file you load by hand.

`confabulation_benchmark.csv` is the **offline fallback** for
`benchmarks/confabulation_benchmark.py`. The script prefers the HuggingFace
dataset `cert-framework/human-confabulation-benchmark`; it falls back here when
`datasets` is not installed or the Hub is unreachable. Before this file
existed the fallback path called `sys.exit(1)`, so the weekly benchmark
workflow failed whenever the Hub call failed.

It is derived mechanically from `src/groundlens/data/reference_pairs.csv`: each
of the 212 rows becomes two rows here, the `grounded_response` with `label=1`
and the `fabricated_response` with `label=0`. There is no `context` column
content, so the fallback exercises the DGI path only.

## Read the number with both hands

Two separate reasons not to quote an AUROC produced from this file:

1. **Authorship confound.** Every grounded response was written by a model from
   a source; every confabulation was written by a person from memory.
   Authorship is perfectly correlated with the label, so a detector can score
   well by recognising who wrote the text. Hold authorship constant and the
   directional score falls to 0.606.
2. **It is the calibration set.** These are the same 212 rows that define the
   bundled DGI reference direction `mu_hat` and the Youden's-J cut `DGI_PASS`.
   Scoring them with the bundled `mu_hat` is scoring a model on its own
   training data. The result is an upper bound on an upper bound.

Use this file to check that the benchmark *runs*. Use the HuggingFace dataset,
with the authorship and length controls, to measure anything.
