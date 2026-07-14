# Benchmark Results

All results use the default embedding model (`all-MiniLM-L6-v2`, 384 dimensions) unless otherwise noted. AUROC is the primary metric.

!!! danger "Retraction, 2026-07"
    The figures previously published on this page (DGI 0.958, domain-calibrated AUROC 0.90–0.99, 87.8% detection on human confabulations, and an NLI baseline near chance) are **withdrawn**.

    All of them rested on evaluations in which the grounded and the confabulated text had **different authors**. Authorship was correlated with the label, so the detectors were being scored on a shortcut. Hold authorship constant and the skill collapses. NLI does not collapse: it is the strongest method at the in-register end, and it is now the recommended second stage.

    The controlled evaluation is in *The Register Wall: What Similarity-Based Hallucination Detectors Actually Measure* (under review). This page reports it.

## The wall

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

With authorship matched, even the best supervised decoder over these embeddings sits in the high 0.6s. **DGI's ≈ 0.68 is not a weak estimator. It is the ceiling of the entire class.** Extra model capacity buys nothing: the MLP, with far more parameters than DGI, reaches 0.675.

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

## What "reproducible" does and does not mean

groundlens scoring is deterministic: the same input gives the same score, forever, on any machine.

Determinism guarantees you get the same number twice. **It does not guarantee the number measures grounding.** That is what the controls in the [evaluation protocol](overview.md) are for, and it is the lesson of the retraction at the top of this page.

```bash
pip install groundlens datasets scikit-learn
groundlens benchmark
```

The bundled benchmark prints a confound warning above its AUROC. Read it.
