# Verifier evaluation

This part measures the **verifiers**, not the infrastructure. GroundLens is the layer
that turns evidence into a signed, checkable decision; which verifiers it runs is a
choice, and any of them can be swapped or added. So their detection quality is
reported here, separately, and never folded into a claim about GroundLens as a whole.

## What is measured

For each verifier (numeric, lexical, NLI, semantic, and any external detector wrapped
as a verifier), on public datasets:

- **FPR at 95% recall** — to catch 95% of hallucinations, how many correct answers are
  wrongly flagged. The number a reviewer lives with, and the one most benchmarks omit.
- **AUROC** and **balanced accuracy** — threshold-free quality and the field's common
  currency, for comparability.

## Datasets

- **RAGTruth** — span-labelled hallucinations over QA, summarisation and data-to-text.
- **LLM-AggreFact** — a broad aggregation of grounding benchmarks.

## How to run

The Colab notebook in this folder loads the datasets, scores each verifier, and
writes the tables and plots. External detectors (for example Vectara HHEM) can be
included as candidate verifiers for a like-for-like comparison. Numbers describe the
verifiers under test on those datasets, on the stated sample size.
