# Retractions

Performance figures published by this project before v3 could not be regenerated
from committed code and data. They are withdrawn. This page says exactly what was
wrong, so that anyone who read or cited them can see what they were actually
looking at.

Nothing here is an apology. Each item is a statement of what a number measured
and why it did not measure what it was labelled as measuring.

The full pre-v3 tree remains available: `git checkout v2.0.0`.

---

## 1. The README performance table

Published on `main` until 10 August 2026:

| Configuration | Model calls | Recall on defects | False alarms | Stability |
|---|---|---|---|---|
| Groundlens rules (domain-configured) | 0 | 0.84 | 0.00 | exact |
| Groundlens rules + geometry | 0 | up to 0.93 | 0.00 | exact |
| Rules on lookup defects | 0 | 1.00 | 0.00 | exact |

Followed by: *"Two of the three most complete evaluations recommend adopting
Groundlens for the output surface."*

**Withdrawn in full.** No dataset, script, evaluation report or citation in any
repository of this project produces these figures. The evaluations referred to
are not named or dated. `BENCHMARKS.md`, which the README pointed to for
caveats, did not exist.

The line immediately beneath the table stated that geometry "has been near
chance" on local factual edits and that "simple baselines can match it". The
table and the prose under it described different products.

---

## 2. SGI and DGI: calibrated on a corpus with no evidence text

`src/groundlens/data/reference_pairs.csv` has 212 rows and these columns:

```
id, domain, question, grounded_response, fabricated_response
```

There is no context column. Not empty — absent. `benchmarks/data/confabulation_benchmark.csv`
does have one, and it is empty in 424 of 424 rows.

Consequences, stated plainly:

- **Every figure computed on that corpus measures question-versus-response
  similarity, not claim-versus-evidence.** That includes DGI 0.712, DGI 0.78 and
  0.81, the 0.606 authorship-matched figure, and the ≈0.68 ceiling. They are real
  computations of a quantity that is not grounding.
- **SGI requires context, so it is not computable from any committed corpus, and
  therefore not calibratable from one.** The shipped constants
  `SGI_STRONG_PASS = 1.20` and `SGI_REVIEW = 0.95` cannot be re-derived from
  anything in this repository. The docstring claiming all thresholds were
  "derived empirically" was not supportable.
- **`DGI_PASS = 0.525` had a real derivation path** — Youden's J over the 212
  rows plus the committed `mu_hat` — but `mu_hat` was fit on the same rows the
  threshold then cut on. The repository's own `benchmarks/data/README.md` called
  this "an upper bound on an upper bound".

The arXiv record is being corrected separately.

---

## 3. The "high 0.6s ceiling" claim

Published as: *"the ceiling of the whole embedding-similarity class is in the
high 0.6s."*

**Withdrawn as an over-generalisation.** This project's own
`docs/benchmarks/results.md` recorded that ≈0.68 "is a measurement on DGI and on
logistic/MLP probes over these embeddings. It is **not** a demonstrated ceiling
for every embedding-similarity method", and noted that random forest and XGBoost
retained signal up to 0.88. The site and the cookbook published as a class-wide
result the exact sentence the benchmark page marked as an over-generalisation.

---

## 4. The rule packs' false-alarm claim

The v2 `eu-retail-banking` pack header stated: *"Measured cost of the whole set
on clean traffic: zero cases changed in either suite."*

**False, and falsifiable by code committed alongside it.** Running the shipped
canary suites:

```
dev    52 cases  clean 20  clean escalated  0
frozen 44 cases  clean 16  clean escalated 16
```

The frozen half — authored blind, before the rule bodies were read — escalates
every clean answer. Ten of those sixteen fail on one rule, `BNK-031`, a substring
search over four hardcoded disclosure phrases that the development canaries
happen to contain and the blind-authored ones do not. The remaining six fail on
attestation metadata the blind author had no way to know to set.

The dev suite's zero false alarms was not a measurement. It was cases written by
someone who had read the predicate.

---

## 5. Smaller items

- `docs/getting-started/cli.md` showed sample output "SGI AUROC 0.8234 (n=150) /
  DGI 0.6810 (n=200)". SGI on 150 items is not possible with zero context rows.
  This was invented sample output.
- `docs/benchmarks/overview.md` listed a benchmark inventory of General 200 /
  Legal 150 / Medical 180 / Financial 120, and listed "context-annotated examples
  (for SGI evaluation)". None of that data was committed.
- The 87.8% figure was retracted in `CHANGELOG.md` and in `docs/benchmarks/results.md`,
  but remained asserted in section 6.2 of the paper PDF shipped in the benchmark
  repository, with no erratum.
- Two of three rows in the homepage table (88–97 / 73–76 / 69–78 percent) rested
  on data that existed in no repository.
- The org description said 215 pairs across 19 domains. The data is 212 rows
  across 9 domains.
- `pyproject.toml` said Apache-2.0 while the GitHub sidebar and README badge said
  MIT. v3 is Apache-2.0 throughout.

---

## What changed structurally

Every one of the items above has the same shape: a number published by the person
whose method it evaluated, checked by nobody, with no committed path from data to
figure.

Three rules now apply, and they are enforced by CI rather than intention:

1. **No figure is published unless a committed, seeded script regenerates it from
   a pinned source revision.** If you cannot name the script, the seed and the
   commit, it does not go out.
2. **No benchmark authored by the person it evaluates counts as evidence of
   capability.** It is a pipeline diagnostic and gets labelled as one.
3. **The structural output is byte-diffed across ten OS × Python combinations on
   every commit.** Behaviour cannot drift silently.

The one thing this project got right before v3 was the frozen canary half — a
held-out set authored blind. It is what produced the 16-of-16 in item 4, and it
is the reason that item could be written at all. That discipline is carried
forward.

*Last updated 10 August 2026.*
