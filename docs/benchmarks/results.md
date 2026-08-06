# Benchmark Results

All results use the default embedding model (`sentence-transformers/sentence-t5-large`, 768 dimensions) unless otherwise noted. AUROC is the primary metric.

!!! danger "Retraction, 2026-07"
    The figures previously published on this page (DGI 0.958, domain-calibrated AUROC 0.90–0.99, 87.8% detection on human confabulations, and an NLI baseline near chance) are **withdrawn**.

    All of them rested on evaluations in which the grounded and the confabulated text had **different authors**. Authorship was correlated with the label, so the detectors were being scored on a shortcut. Hold authorship constant and the skill collapses. NLI does not collapse: it is the strongest method at the in-register end, and it is now the recommended second stage.

    The controlled evaluation is the register-alignment result ("The Register Wall"), reported in
    *The Outer Geometry of Truth: Register Alignment and the Limits of Embedding-Based Hallucination
    Detection*. That paper is an arXiv preprint, newer than papers 1--3 and not yet announced; unlike
    them it has not been through a venue review cycle, and it is not accepted anywhere. This page
    reports it.

## The wall

**Register** here means how closely a wrong answer imitates the style of a right one: same vocabulary, same phrasing, same sentence structure, one wrong fact. An out-of-register confabulation reads oddly and is easy to catch. An in-register one reads exactly like a good answer, and that is the case that matters in production.

Bin confabulations by how far they sit from the register of a correct answer, and every distributional and embedding-similarity detector, ours included, declines toward chance as the confabulation moves **into** register: same vocabulary, same phrasing, same structure, one wrong fact.

| Detector | Out of register | In register |
|---|--:|--:|
| NLI cross-encoder (supervised) | 0.836 | **0.887** |
| Classic encoders (MiniLM, mpnet, bge, gte) | 0.70 – 0.74 | **0.62 – 0.68** |
| Raw cosine | 0.726 | **0.595** |

Entailment does not decline. It is strongest exactly where geometry is weakest. That is not a defeat: it is the division of labour that makes the two-stage design work.

## The ceiling, and the authorship shortcut

A detector that appears to beat the wall is usually reading **who wrote the text**, not whether it is grounded. In the human-confabulated benchmark the grounded answers come from a source and the confabulations were written by a person from memory, so authorship is perfectly correlated with the label.

Hold authorship constant and the skill disappears:

| Detector | Uncontrolled | Authorship matched |
|---|--:|--:|
| Large instruction-tuned embedder | ≈ 0.99 | shortcut, not skill |
| Logistic probe | 0.932 | **0.660** |
| MLP | 0.935 | **0.675** |
| Directional score (DGI) | high | **0.606** |

With authorship matched, DGI and the logistic and MLP probes over these embeddings sit in the high 0.6s. **DGI's ≈ 0.68 is not a weak estimator. It is the measured ceiling for DGI and for those probes.** Extra capacity of that kind buys nothing: the MLP, with far more parameters than DGI, reaches 0.675.

!!! warning "How far this ceiling generalises"
    ≈ 0.68 is a **measurement on DGI and on logistic/MLP probes over these embeddings**. It is not a
    demonstrated ceiling for every embedding-similarity method. Stronger classifiers (random forest,
    XGBoost) retain residual signal up to **0.88** at high register alignment.

    The authorship control was run on DGI and on those probes. **It was not run on SGI**, which scores
    against a supplied source and is a different method. Nothing on this page is an authorship-controlled
    SGI number.

## Calibration, corrected

Domain calibration moves the operating point, not the wall.

| | Overall | Out-of-register bin | In-register bin |
|---|--:|--:|--:|
| Generic | 0.684 | 0.717 | 0.626 |
| Domain-calibrated | 0.736 | **0.815** | 0.689 |

Almost the entire gain lands where the problem was already easy. The in-register bin, the one that matters in production, moves 0.626 → 0.689.

!!! warning "Calibrate to set your escalation rate"
    Calibration decides *how much* you send to the second stage. It does not decide *what you can see*. Do not calibrate expecting the blind spot to close.

## External benchmarks, length-matched

| Benchmark | Apparent | After control |
|---|--:|--:|
| RAGTruth-QA | 0.705 | **0.634** (length-matched) |
| FaithBench | 0.620 | **0.500** |
| TruthfulQA | — | chance |

RAGTruth's apparent skill was a length artifact: the grounded and hallucinated responses differ in median length (146 vs 92 words), and the rank correlation between score and length is −0.70. Match the lengths and it falls from 0.676 to 0.634.

## SGI: pending

| Benchmark | Reported | Status |
|---|--:|---|
| HaluEval QA (n = 10,000) | 0.805 (mean over 5 encoders) | **Pending the authorship and length controls** |
| FACTS Grounding (provenance) | ≈ 0.95 | **Pending.** The two arms differ in generation condition, which is the shortcut the controls exist to expose. Labels are LLM-judge derived. |

SGI, with context, is the road forward. Its numbers predate the controls and have not been re-run under them. Treat them as provisional, and do not quote them as validated.

## From the Outer Geometry paper (not yet reproducible)

These figures come from the register-alignment result ("The Register Wall"): *The Outer Geometry of Truth: Register Alignment and the Limits of Embedding-Based Hallucination Detection*. **The notebooks, the authorship-matched split and the Lean 4 file are not yet released**, so nothing in this section can be re-run from this repository today. Cite the manuscript, not this page.

| Result | Value |
|---|--:|
| DGI overall AUROC, TruthfulQA | 0.897 |
| DGI overall AUROC, GL-212 | 0.712 |
| DGI overall AUROC, RAGTruth | 0.617 |
| Rank correlation, register alignment vs AUROC | Spearman −0.90 across 15 quintile points |
| Cross-encoder control | Spearman −1.00 in 4 of 6 dataset/direction pairs |
| Corpus | 6,487 pairs (GL-212 212, TruthfulQA 2,275, RAGTruth 4,000) |
| Lean 4 verified core | 3 lemmas, clean `#print axioms`, no `sorryAx` — available on request |

The Spearman −0.90 is the paper's central claim: AUROC falls as register alignment rises, monotonically, across 15 quintile points. The cross-encoder control reproduces that decline with a different scoring family, reaching Spearman −1.00 in four of the six dataset/direction pairs, which is what rules out an artefact of one embedding panel.

!!! danger "These are pooled, uncontrolled numbers. Read them with the scope rules."
    - **0.897 on TruthfulQA is a DGI number.** The SGI TruthfulQA result is AUC 0.478 (arXiv:2512.13771). The two are different methods on different setups and must never be quoted as if they were the same measurement.
    - These are **pooled overall AUROCs, not authorship- or length-matched**. They are the input to the register-binned analysis, not a refutation of it. The controlled figures are in the tables above, and those are the ones to quote as performance.
    - This page also reports TruthfulQA at chance under the length-matched external protocol above. That evaluation and this one use different corpora, different pairings and different controls, and **the discrepancy is not yet reconciled in print**. Until the notebooks are released, treat it as open rather than picking whichever number is more convenient.
    - Register sufficiency is an assumption in that paper, not a theorem, and only partially true: after register alignment is controlled, residual surface features still carry rank correlation up to Spearman 0.37.
    - The formal bound covers only detectors that are functions of a **single frozen sentence embedding** — not activations, not log-probabilities, not multi-sample methods, not retrieval.

## What "reproducible" does and does not mean

groundlens scoring is deterministic: the same input gives the same score, forever, on any machine.

Determinism guarantees you get the same number twice. **It does not guarantee the number measures grounding.** That is what the controls in the [evaluation protocol](overview.md) are for, and it is the lesson of the retraction at the top of this page.

```bash
pip install groundlens datasets scikit-learn
groundlens benchmark
```

The bundled benchmark prints a confound warning above its AUROC. Read it.
