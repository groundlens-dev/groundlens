# SGI: Semantic Grounding Index

The Semantic Grounding Index (SGI) measures whether an LLM response engaged with provided source context or stayed semantically anchored to the question. It is the primary scoring method for **RAG verification** --- any scenario where you have a question, retrieved context, and a generated response.

**Paper**: Marin (2025). *Semantic Grounding Index for LLM Hallucination Detection*. [arXiv:2512.13771](https://arxiv.org/abs/2512.13771).

## Formula

$$
\text{SGI} = \frac{d(\phi(r), \phi(q))}{d(\phi(r), \phi(\text{ctx}))}
$$

where:

- $\phi(\cdot)$ is the sentence embedding function (default: `sentence-transformers/sentence-t5-large`)
- $d(\cdot, \cdot)$ is Euclidean distance in $\mathbb{R}^n$
- $r$ is the LLM response
- $q$ is the input question
- $\text{ctx}$ is the source context

## Geometric Interpretation

SGI is a **relative proximity measure**. It compares how far the response embedding is from the question versus how far it is from the context:

- **SGI > 1**: The response is closer to the context than to the question. This suggests the LLM engaged with the source material and incorporated its content.
- **SGI = 1**: The response is equidistant from both. Ambiguous.
- **SGI < 1**: The response is closer to the question than to the context. This suggests the LLM may have generated an answer from its parametric memory rather than the provided context.

Geometrically, the SGI = 1 boundary is the **perpendicular bisector hyperplane** between the question and context embeddings. Responses on the context side of this hyperplane score above 1; responses on the question side score below 1.

## Threshold Zones

| Zone | SGI Range | Level | Interpretation | Action |
|---|---|---|---|---|
| Grounded | SGI >= 1.20 | `ok` | Response strongly engaged with context | Accept |
| Partly | 0.95 <= SGI < 1.20 | `review` | Some context influence detected | Review recommended |
| Not grounded | SGI < 0.95 | `risk` | Weak context engagement | Human review required |

These thresholds are the ones bundled for the default encoder (`sentence-transformers/sentence-t5-large`). If you change the encoder, re-fit them with [`fit_thresholds`](calibration.md).

!!! example "Two real readings"
    With the default encoder, a faithful answer that restates the source scored **3.34** and read *"Supported by the document"*. An on-topic answer that contradicts the source scored **1.17** and read *"Partly supported"*: it stayed in the topic's neighborhood, so geometry placed it in the review band rather than the risk band.

    This is the caveat that matters: SGI measures **grounding, not truth**. A plausible wrong fact stated in the right frame can still score above the pass threshold, because it sits close to the source in embedding space. SGI tells you whether an answer was drawn from the source, not whether it is correct.

## Normalization

The raw SGI score is normalized to [0, 1] using a tanh mapping:

$$
\text{SGI}_{\text{norm}} = \tanh\bigl(\max(0,\; \text{SGI} - 0.3)\bigr)
$$

Reference points:

| Raw SGI | Normalized |
|---|---|
| 0.30 | 0.000 |
| 0.95 | 0.457 |
| 1.20 | 0.604 |
| 2.00 | 0.885 |

## When to Use SGI

SGI is the right choice when you have **all three inputs**:

- A question or prompt
- Retrieved context, source documents, or reference text
- The LLM's response

Common scenarios:

- **RAG pipelines**: Verify the LLM used the retrieved chunks
- **Document Q&A**: Confirm answers cite the source material
- **Summarization**: Check the summary reflects the input document
- **Grounded generation**: Any task where you provide context and expect the model to use it

## Limitations

!!! warning "SGI measures engagement, not correctness"
    SGI detects whether the response is semantically similar to the context. A response that *paraphrases the context incorrectly* might still score well on SGI if it uses similar vocabulary and concepts. SGI catches the case where the LLM **ignores** the context entirely --- it does not verify that the response **accurately** represents the context.

!!! warning "Context quality matters"
    If the retrieved context is irrelevant to the question, a high SGI score means the response is close to irrelevant material. SGI assumes the context is appropriate --- retrieval quality is a separate concern.

!!! warning "Short text sensitivity"
    Very short texts (1--3 words) produce embeddings with less discriminative power. SGI works best with texts of at least one full sentence.

## API Reference

```python
from groundlens import compute_sgi, SGI

# Function API
result = compute_sgi(
    question="What is the capital of France?",
    context="France is in Western Europe. Its capital is Paris.",
    response="The capital of France is Paris.",
    model="sentence-transformers/sentence-t5-large",  # optional
)

# Class API (reusable)
sgi = SGI(model="sentence-transformers/sentence-t5-large")
result = sgi.score(
    question="What is X?",
    context="X is Y.",
    response="X is Y.",
)
```

The `SGIResult` contains:

| Field | Type | Description |
|---|---|---|
| `value` | `float` | Raw SGI score |
| `normalized` | `float` | Score in [0, 1] |
| `flagged` | `bool` | True if below review threshold |
| `q_dist` | `float` | Euclidean distance to question embedding |
| `ctx_dist` | `float` | Euclidean distance to context embedding |
| `method` | `str` | Always `"sgi"` |
| `explanation` | `str` | Human-readable interpretation |
