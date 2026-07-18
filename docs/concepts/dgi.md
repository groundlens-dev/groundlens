# DGI: Directional Grounding Index

The Directional Grounding Index (DGI) evaluates whether an LLM response follows the characteristic semantic displacement pattern of grounded responses --- **without requiring any source context**. It needs only a question and a response, plus calibration data defining the "grounded direction."

**Paper**: Marin (2026). *A Geometric Taxonomy of Hallucinations in LLMs*. [arXiv:2602.13224](https://arxiv.org/pdf/2602.13224v3).

## Formula

$$
\delta = \phi(r) - \phi(q)
$$

$$
\text{DGI} = \frac{\delta}{\|\delta\|} \cdot \hat{\mu}
$$

where:

- $\phi(\cdot)$ is the sentence embedding function
- $\delta$ is the **displacement vector** from question to response in embedding space
- $\hat{\mu}$ is the **reference direction** --- the mean displacement direction computed from verified grounded (question, response) pairs

## Geometric Interpretation

DGI measures the **cosine similarity** between the displacement direction of the current (question, response) pair and the average displacement direction of known-grounded pairs.

- **DGI > 0.30**: The displacement aligns with the grounded reference direction. The response moves through embedding space in the same way that verified factual answers do.
- **0 < DGI < 0.30**: Weak alignment. The displacement partially follows grounded patterns but with significant deviation.
- **DGI < 0**: The displacement is opposite to the grounded direction. This is a strong risk signal.

!!! abstract "Intuition"
    When an LLM produces a grounded answer to a question, it performs a characteristic semantic transformation: moving from the "question space" toward the "factual elaboration space." This movement has a consistent direction across different questions. Hallucinated answers move differently --- they tend to elaborate in ways that do not follow this grounded trajectory.

## The Reference Direction

The reference direction $\hat{\mu}$ is the maximum-likelihood estimate of the mean direction parameter of a **von Mises-Fisher distribution** on the unit hypersphere $S^{n-1}$. It is computed as:

1. Collect $N$ verified (question, response) pairs where the response is known to be grounded.
2. For each pair $i$, compute $\delta_i = \phi(r_i) - \phi(q_i)$.
3. Normalize each displacement: $\hat{\delta}_i = \delta_i / \|\delta_i\|$.
4. Average the unit vectors and re-normalize: $\hat{\mu} = \text{normalize}\bigl(\frac{1}{N}\sum_i \hat{\delta}_i\bigr)$.

## Calibration and AUROC

DGI accuracy depends heavily on the quality of $\hat{\mu}$:

| Calibration | Typical AUROC | When to use |
|---|---|---|
| Generic (bundled dataset) | 0.684 overall / 0.626 in-register | Quick evaluation, prototyping |
| Domain-specific (20--100 pairs) | 0.736 overall / 0.689 in-register | Production triage |

The bundled dataset provides a general-purpose reference direction trained on diverse question-answer pairs. Domain-specific calibration produces a $\hat{\mu}$ that captures the particular displacement patterns of your domain (e.g., legal, medical, financial), dramatically improving discrimination.

!!! tip "Calibration is the single biggest lever for DGI accuracy"
    Going from generic to domain-specific calibration typically improves AUROC by 0.14--0.23 points. See the [Domain Calibration Guide](../guides/domain-calibration.md) for step-by-step instructions.

## Threshold Zones

| Zone | DGI Range | Interpretation | Action |
|---|---|---|---|
| Pass | DGI >= 0.30 | Aligned with grounded patterns | Accept |
| Flagged | 0.00 <= DGI < 0.30 | Weak alignment | Human review |
| High risk | DGI < 0.00 | Opposes grounded direction | Likely hallucination |

## Normalization

DGI raw scores are in [-1, 1] (cosine similarity range). Linear normalization to [0, 1]:

$$
\text{DGI}_{\text{norm}} = \frac{\text{DGI} + 1}{2}
$$

| Raw DGI | Normalized |
|---|---|
| -1.0 | 0.000 |
| 0.0 | 0.500 |
| 0.3 | 0.650 |
| 1.0 | 1.000 |

## When to Use DGI

DGI is the right choice when you **do not have source context**:

- **Chat/dialogue verification**: No retrieval context available
- **Agent self-verification**: Agents checking their own outputs before returning results
- **Batch evaluation**: Scoring large datasets of LLM outputs at scale
- **Pre-deployment testing**: Evaluating model quality before release

## Limitations

!!! warning "Distributional hypothesis boundary"
    DGI operates on the distributional hypothesis: words (and sentences) that appear in similar contexts have similar meanings. This means DGI cannot distinguish between a factually correct statement and a **human-crafted confabulation** that mimics the distributional properties of a grounded response. See [Confabulation Boundary](../theory/confabulation-boundary.md) for the full analysis.

!!! warning "Calibration sensitivity"
    Calibration moves the operating point, not the wall: overall AUROC 0.684 → 0.736, with the gain at the easy out-of-register end (0.717 → 0.815) and the in-register bin moving only 0.626 → 0.689. Calibrate for production, but do not expect it to close the blind spot. With authorship held constant DGI reaches 0.606, and ≈ 0.68 is the ceiling of the entire embedding-similarity class, not a target to beat.

!!! warning "Displacement magnitude"
    The DGI *score* considers only the *direction* of displacement, not its *magnitude*. A response very similar to the question (small displacement) might score well on DGI purely by chance of direction alignment. The degenerate case (identical question and response) produces a zero displacement vector and is automatically flagged. The magnitude itself is still returned on `DGIResult.magnitude` (see below) — it does not enter the score, but it is available as a second signal (how far the response moved from the question).

## API Reference

```python
from groundlens import compute_dgi, DGI

# Function API
result = compute_dgi(
    question="What causes seasons on Earth?",
    response="Seasons are caused by Earth's 23.5-degree axial tilt.",
    model="all-MiniLM-L6-v2",        # optional
    reference_csv="domain_pairs.csv",  # optional
)

# Class API (reusable, with custom calibration)
dgi = DGI(reference_csv="my_domain_pairs.csv")
result = dgi.score(
    question="What is X?",
    response="X is Y.",
)

# Inline calibration
dgi = DGI()
dgi.calibrate(pairs=[("Q1?", "A1."), ("Q2?", "A2."), ...])
result = dgi.score(question="Q?", response="A.")
```

The `DGIResult` contains:

| Field | Type | Description |
|---|---|---|
| `value` | `float` | Raw DGI score = *direction* (cosine similarity to reference direction) |
| `magnitude` | `float` | `\|\|phi(response) - phi(question)\|\|` — how far the response moved from the question. Not used by the score; a second signal. |
| `normalized` | `float` | Score in [0, 1] |
| `flagged` | `bool` | True if below pass threshold |
| `method` | `str` | Always `"dgi"` |
| `explanation` | `str` | Human-readable interpretation |

## DGI depends on the encoder more than SGI

DGI works by checking whether the step from question to answer points in the same direction as known grounded answers. That direction is learned from data and lives in one specific embedding space. Change the encoder and the direction has to be relearned, and some encoders simply do not lay grounded and ungrounded answers along a clean direction.

In our reasoning-chains benchmark, DGI ran through seven base language models used as encoders and stayed near chance on all of them, while SGI still showed the expected pattern. The practical takeaway is short: SGI is the safer default when you are unsure about your encoder, and DGI should be calibrated and measured on your own data before you trust it. See [Custom encoders](../guides/custom-encoders.md) and the reasoning-chains benchmark in the project README.
