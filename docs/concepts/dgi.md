# DGI: Directional Grounding Index

The Directional Grounding Index (DGI) evaluates whether an LLM response follows the characteristic semantic displacement pattern of grounded responses, **without requiring any source context**. It needs only a question and a response, plus calibration data defining the "grounded direction."

**Paper**: Marin (2026). *A Geometric Taxonomy of Hallucinations in LLMs*. [arXiv:2602.13224](https://arxiv.org/pdf/2602.13224v3).

## Formula

$$
\delta = \phi(r) - \phi(q)
$$

$$
\text{DGI} = \frac{\delta}{\|\delta\|} \cdot \hat{\mu}
$$

where:

- $\phi(\cdot)$ is the sentence embedding function (default encoder: `sentence-transformers/sentence-t5-large`, 768-dimensional)
- $\delta$ is the **displacement vector** from question to response in embedding space
- $\hat{\mu}$ is the **reference direction**, the mean displacement direction computed from verified grounded (question, response) pairs

## Geometric interpretation

DGI is the **cosine similarity** between the displacement direction of the current (question, response) pair and the average displacement direction of known grounded pairs. When an LLM answers a question with a grounded response, it performs a characteristic move in embedding space, from the question toward its factual elaboration, and that move has a consistent direction across questions. A fabrication tends to move differently.

Read DGI against a single calibrated cut:

- **At or above the cut**: the displacement aligns with the grounded reference direction. Reads as grounded.
- **Below the cut**: the displacement does not follow the grounded direction. Reads as a risk to send to the second stage.

With the default encoder the cut is **0.525** for the global reference direction and **0.545** for the local variant described below. These cut points are not universal: they depend on the encoder and on the style of your data, so treat DGI as a relative ranking and set the operating point by calibrating on your own grounded set.

## Two real readings

Measured with the default encoder on the shipped reference set:

| Question | Answer | DGI | Reading |
|---|---|---|---|
| What is the difference between a traditional IRA and a Roth IRA? | A correct explanation of the tax treatment | 0.54 | Looks grounded |
| What is the primary function of red blood cells? | A fabricated answer about "red coloration" | 0.37 | Not grounded |

The grounded answer lands above the 0.525 cut; the fabrication lands below it.

## The reference direction

The reference direction $\hat{\mu}$ is the maximum-likelihood estimate of the mean direction of a **von Mises-Fisher distribution** on the unit hypersphere $S^{n-1}$. It is computed as:

1. Collect $N$ verified (question, response) pairs where the response is known to be grounded.
2. For each pair $i$, compute $\delta_i = \phi(r_i) - \phi(q_i)$.
3. Normalize each displacement: $\hat{\delta}_i = \delta_i / \|\delta_i\|$.
4. Average the unit vectors and re-normalize: $\hat{\mu} = \text{normalize}\bigl(\frac{1}{N}\sum_i \hat{\delta}_i\bigr)$.

The library ships a reference direction computed this way from a bundled set of 212 grounded/fabricated pairs across nine domains (`reference_pairs.csv`). It is recomputed from that file, so the shipped direction is reproducible by construction rather than a frozen vector you have to trust.

### The grounded direction is not a single global vector

The mean direction $\hat{\mu}$ above treats "being grounded" as one fixed direction for all questions. It is not. The direction that separates grounded from fabricated answers **varies by domain**: a finance question and a medical question move through embedding space along related but distinct grounded directions. A single global $\hat{\mu}$ averages over that structure and leaves signal on the table.

The **local variant** $\Gamma_k$ exploits this. Instead of one global direction, it builds a query-specific reference from the $k$ calibration questions nearest to yours, and measures your displacement against that local direction:

```python
from groundlens import compute_dgi, check

# global reference direction
reading = check(compute_dgi(question=question, response=response))

# local variant: reference built from the k nearest calibration questions
reading_local = check(compute_dgi(question=question, response=response, k=10))
```

On the shipped reference set (leave-one-out) this raises detection from **AUROC 0.78** with the global direction to **0.81** with the local variant. The gain is largest when your calibration set spans several domains, because that is exactly when a single global direction is the poorest fit. Note that this set is not authorship-controlled; under the stricter authorship control the register wall lowers the ceiling for the whole embedding-similarity class (see [Benchmarks](../benchmarks/overview.md)).

## Calibration

DGI depends heavily on the quality of $\hat{\mu}$ and on the encoder. Calibrate it on your own labelled grounded set and pick the operating point with `fit_thresholds` (which uses Youden's J to place the cut). Calibration moves the operating point; it does not remove the blind spot below. See the [Domain Calibration Guide](../guides/domain-calibration.md).

## Normalization

DGI raw scores are in [-1, 1] (cosine similarity range). Linear normalization to [0, 1]:

$$
\text{DGI}_{\text{norm}} = \frac{\text{DGI} + 1}{2}
$$

| Raw DGI | Normalized |
|---|---|
| -1.0 | 0.000 |
| 0.0 | 0.500 |
| 0.525 | 0.763 |
| 1.0 | 1.000 |

## When to use DGI

DGI is the right choice when you **do not have source context**:

- **Chat / dialogue verification**: no retrieval context available
- **Agent self-verification**: agents checking their own outputs before returning results
- **Batch evaluation**: scoring large datasets of LLM outputs at scale
- **Pre-deployment testing**: evaluating model quality before release

## Limitations

!!! warning "Grounding, not truth"
    DGI measures whether a response moves like a grounded one, not whether it is true. It cannot distinguish a factually correct statement from a confabulation that mimics the displacement of a grounded response (an in-frame factual error). This is a fundamental limit of the embedding-similarity class, not a tuning problem. See [Confabulation Boundary](../theory/confabulation-boundary.md) and hand off these cases to the [second stage](../guides/second-stage.md).

!!! warning "Encoder and domain sensitivity"
    The grounded direction is learned and lives in one specific embedding space. Change the encoder and the direction has to be relearned, and some encoders do not lay grounded and ungrounded answers along a clean direction at all. DGI leans on the encoder and the domain far more than SGI does. Calibrate and measure it on your own data before you trust it.

!!! warning "Displacement magnitude"
    The DGI *score* uses only the *direction* of displacement, not its *magnitude*. A response very similar to the question (small displacement) might score well by chance of alignment. The degenerate case (identical question and response) produces a zero displacement vector and is automatically flagged. The magnitude is still returned on `DGIResult.magnitude` as a second signal (how far the response moved from the question); it does not enter the score.

## API reference

```python
from groundlens import compute_dgi, DGI

# Function API
result = compute_dgi(
    question="What causes seasons on Earth?",
    response="Seasons are caused by Earth's 23.5-degree axial tilt.",
    model="sentence-transformers/sentence-t5-large",   # optional
    reference_csv="domain_pairs.csv",                  # optional
    k=10,                                              # optional: local variant
)

# Class API (reusable, with custom calibration)
dgi = DGI(reference_csv="my_domain_pairs.csv")
result = dgi.score(question="What is X?", response="X is Y.")

# Inline calibration
dgi = DGI()
dgi.calibrate(pairs=[("Q1?", "A1."), ("Q2?", "A2.")])
result = dgi.score(question="Q?", response="A.")
```

The `DGIResult` contains:

| Field | Type | Description |
|---|---|---|
| `value` | `float` | Raw DGI score, the *direction* (cosine similarity to the reference direction) |
| `magnitude` | `float` | `\|\|phi(response) - phi(question)\|\|`, how far the response moved from the question. Not used by the score; a second signal. |
| `normalized` | `float` | Score in [0, 1] |
| `flagged` | `bool` | True if below the pass threshold |
| `method` | `str` | Always `"dgi"` |
| `explanation` | `str` | Plain-language interpretation |

## DGI depends on the encoder more than SGI

DGI works by checking whether the step from question to answer points in the same direction as known grounded answers. That direction is learned from data and lives in one specific embedding space. Change the encoder and the direction has to be relearned, and some encoders simply do not lay grounded and ungrounded answers along a clean direction.

In our reasoning-chains benchmark, DGI ran through seven base language models used as encoders and stayed near chance on all of them, while SGI still showed the expected pattern. The practical takeaway is short: SGI is the safer default when you are unsure about your encoder, and DGI should be calibrated and measured on your own data before you trust it. See [Custom encoders](../guides/custom-encoders.md) and the reasoning-chains benchmark in the project README.
