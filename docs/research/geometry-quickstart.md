# Geometry quickstart

!!! note "This is the research side of Groundlens"
    Geometry is optional and is not what Groundlens is for. The product entry point is
    [`check()`](../getting-started/quickstart.md), which checks obligations, deadlines,
    amounts and citations against your sources and your rule packs. Everything on this
    page needs `pip install "groundlens[geometry]"`.

This guide walks through the three main ways to use the geometric scores: SGI (with context), DGI (without context), and the unified `evaluate()` function that auto-selects the right method.

## Your First SGI Check

SGI (Semantic Grounding Index) evaluates whether an LLM response engaged with provided source context. Use it when you have retrieval context available --- the typical RAG verification scenario.

```python
from groundlens import compute_sgi

result = compute_sgi(
    question="What is the capital of France?",
    context="France is in Western Europe. Its capital is Paris.",
    response="The capital of France is Paris.",
)

print(f"SGI Score:    {result.value:.4f}")
print(f"Normalized:   {result.normalized:.4f}")
print(f"Flagged:      {result.flagged}")
print(f"Explanation:  {result.explanation}")
print(f"Q distance:   {result.q_dist:.4f}")
print(f"Ctx distance: {result.ctx_dist:.4f}")
```

!!! success "Interpreting SGI scores"
    - **SGI > 1.20**: Strong context engagement --- the response is significantly closer to the context than to the question. Green zone.
    - **0.95 < SGI < 1.20**: Partial engagement --- some context influence detected but not definitive. Review recommended.
    - **SGI < 0.95**: Weak context engagement --- the response may be ignoring the retrieved context. Flagged for human review.

## Your First DGI Check

DGI (Directional Grounding Index) evaluates grounding without any context. Use it when you only have a question and a response --- chat/dialogue verification, agent self-checks, or batch evaluation.

```python
from groundlens import compute_dgi

result = compute_dgi(
    question="What causes seasons on Earth?",
    response="Seasons are caused by Earth's 23.5-degree axial tilt.",
)

print(f"DGI Score:    {result.value:.4f}")   # direction: alignment with grounded reference
print(f"Magnitude:    {result.magnitude:.4f}") # how far the response moved from the question
print(f"Normalized:   {result.normalized:.4f}")
print(f"Flagged:      {result.flagged}")
print(f"Explanation:  {result.explanation}")
```

!!! success "Interpreting DGI scores"
    DGI is a **single binary cut**, not a set of bands. `compute_dgi` computes
    `flagged = value < DGI_PASS` and nothing else.

    - **DGI >= 0.525** (`DGI_PASS`): the displacement aligns with grounded
      response patterns. Pass.
    - **DGI < 0.525**: the displacement diverges from grounded patterns. Flagged.

    0.525 is the Youden's-J operating point for the default encoder
    (`sentence-transformers/sentence-t5-large`) on the bundled 212-pair
    reference set. It is encoder- and domain-specific: recalibrate with
    [`fit_thresholds`](../api/index.md) on your own data. Read the value from
    the code rather than copying it:

    ```python
    from groundlens._internal.thresholds import DGI_PASS   # 0.525
    ```

## Plain-language checks

The raw score and flag above are built for pipelines. For a reading a person can act on, pass any result to `render_check()`. In 1.x this function was called `check()`; that name now belongs to the product entry point, so the renderer moved to `groundlens.geometry.render`. It is the single source of truth for wording — the README and the [MCP servers](https://github.com/groundlens-dev/groundlens-mcp) render from the same function.

```python
from groundlens import compute_sgi, compute_dgi
from groundlens.geometry.render import render_check

sgi = compute_sgi(
    question="What is the Bizum daily limit?",
    context="The daily Bizum transfer limit is 1,000 EUR per transaction.",
    response="The Bizum daily limit is 500 EUR. Premium clients have 10,000 EUR.",
)
print(render_check(sgi).render())
# CHECK: Not supported by the document (Semantic Grounding Index - SGI=0.83)
# The answer stays closer to the question than to the source, so it may not
# come from the document. Check it before trusting it.

dgi = compute_dgi(
    question="What causes seasons on Earth?",
    response="Seasons are caused by Earth's 23.5-degree axial tilt.",
)
print(render_check(dgi).render())
# CHECK: Not grounded (Directional Grounding Index - DGI=0.41)
# The answer does not move the way grounded answers do. Check it before trusting it.
#
# 0.41 is below DGI_PASS (0.525), so it reads as not grounded even though the
# answer is correct. That is the DGI limitation, not a bug: the bundled
# reference direction was fitted on 212 answers written in one style, and text
# written any other way scores low however faithful it is. Calibrate on your
# own corpus before relying on DGI, or use SGI where you have a source.
# No source given — judged by the shape of the answer.
```

!!! note "What the check is (and isn't)"
    The check **level** (`ok` / `review` / `risk`, on `render_check(...).level`) comes only from the calibrated thresholds. The **label** and **message** are jargon-free: "grounding" and "hallucination" never appear in what a user reads. The raw components (`q_dist` / `ctx_dist` for SGI, the displacement `magnitude` for DGI) are on `render_check(...).detail`. A check is a statement about whether the answer is *drawn from the source*, not about whether it is *factually correct*.

## Auto-Select with evaluate()

The `evaluate()` function automatically selects SGI or DGI based on whether context is provided:

```python
from groundlens import evaluate

# With context -> SGI
score = evaluate(
    question="What is photosynthesis?",
    response="Photosynthesis converts light energy into chemical energy.",
    context="Plants use photosynthesis to convert sunlight into glucose.",
)
print(f"Method: {score.method}")  # 'sgi'

# Without context -> DGI
score = evaluate(
    question="What is photosynthesis?",
    response="Photosynthesis converts light energy into chemical energy.",
)
print(f"Method: {score.method}")  # 'dgi'
```

The `GroundlensScore` returned by `evaluate()` is a unified container:

```python
score.value        # Raw score (SGI ratio or DGI cosine similarity)
score.normalized   # Mapped to [0, 1]
score.flagged      # the hard cut only; False across the whole review band
render_check(score).escalate  # True for the review band too -- branch on this
score.method       # 'sgi' or 'dgi'
score.explanation  # Human-readable interpretation
score.detail       # Full SGIResult or DGIResult
```

`render_check()` accepts a `GroundlensScore` directly, so the same plain-language reading works after `evaluate()`:

```python
from groundlens import evaluate
from groundlens.geometry.render import render_check

score = evaluate(question="...", response="...", context="...")
print(render_check(score).render())
```

## Reusable Scorer Objects

For repeated evaluations, use the class-based API to avoid passing `model` every time:

```python
from groundlens import SGI, DGI

# SGI scorer
sgi = SGI(model="sentence-transformers/sentence-t5-large")
result = sgi.score(
    question="What is X?",
    context="X is defined as Y in the specification.",
    response="X is Y.",
)

# DGI scorer with custom calibration
dgi = DGI(reference_csv="my_domain_pairs.csv")
result = dgi.score(
    question="What is X?",
    response="X is Y.",
)
```

## Batch Evaluation

Evaluate multiple items at once:

```python
from groundlens import evaluate_batch

items = [
    {
        "question": "What is the capital of France?",
        "response": "The capital of France is Paris.",
        "context": "Paris is the capital of France.",
    },
    {
        "question": "What causes tides?",
        "response": "Tides are caused by the Moon's gravity.",
    },
]

results = evaluate_batch(items)

for i, score in enumerate(results):
    print(f"Item {i}: {score.method} = {score.value:.3f}, flagged={score.flagged}")
```

## What Next?

- [CLI Reference](../getting-started/cli.md) --- run groundlens from the command line
- [How It Works](../concepts/how-it-works.md) --- understand the geometry behind the scores
- [Domain Calibration](../guides/domain-calibration.md) --- what calibration does, and what it does not fix
- [RAG Verification](../guides/rag-verification.md) --- integrate SGI into your RAG pipeline
