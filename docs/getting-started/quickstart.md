# Quickstart

This guide walks through the three main ways to use groundlens: SGI (with context), DGI (without context), and the unified `evaluate()` function that auto-selects the right method.

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
    - **DGI > 0.30**: Displacement aligns with grounded response patterns. Pass.
    - **0.00 < DGI < 0.30**: Weak alignment --- the response diverges from typical grounded patterns. Flagged.
    - **DGI < 0.00**: Displacement opposes the grounded direction. High risk.

## Plain-language checks

The raw score and flag above are built for pipelines. For a reading a person can act on, pass any result to `check()`. It is the single source of truth for wording — the README and the [MCP servers](https://github.com/groundlens-dev/groundlens-mcp) render from the same function.

```python
from groundlens import compute_sgi, compute_dgi, check

sgi = compute_sgi(
    question="What is the Bizum daily limit?",
    context="The daily Bizum transfer limit is 1,000 EUR per transaction.",
    response="The Bizum daily limit is 500 EUR. Premium clients have 10,000 EUR.",
)
print(check(sgi).render())
# CHECK: Not supported by the document (Semantic Grounding Index - SGI=0.83)
# The answer stays closer to the question than to the source, so it may not
# come from the document. Check it before trusting it.

dgi = compute_dgi(
    question="What causes seasons on Earth?",
    response="Seasons are caused by Earth's 23.5-degree axial tilt.",
)
print(check(dgi).render())
# CHECK: Looks grounded (Directional Grounding Index - DGI=0.41)
# The answer moves the way well-grounded answers usually do.
# No source given — judged by the shape of the answer.
```

!!! note "What the check is (and isn't)"
    The check **level** (`ok` / `review` / `risk`, on `check(...).level`) comes only from the calibrated thresholds. The **label** and **message** are jargon-free: "grounding" and "hallucination" never appear in what a user reads. The raw components (`q_dist` / `ctx_dist` for SGI, the displacement `magnitude` for DGI) are on `check(...).detail`. A check is a statement about whether the answer is *drawn from the source*, not about whether it is *factually correct*.

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
score.flagged      # Boolean: needs human review?
score.method       # 'sgi' or 'dgi'
score.explanation  # Human-readable interpretation
score.detail       # Full SGIResult or DGIResult
```

`check()` accepts a `GroundlensScore` directly, so the same plain-language reading works after `evaluate()`:

```python
from groundlens import evaluate, check

score = evaluate(question="...", response="...", context="...")
print(check(score).render())
```

## Reusable Scorer Objects

For repeated evaluations, use the class-based API to avoid passing `model` every time:

```python
from groundlens import SGI, DGI

# SGI scorer
sgi = SGI(model="all-MiniLM-L6-v2")
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

- [CLI Reference](cli.md) --- run groundlens from the command line
- [How It Works](../concepts/how-it-works.md) --- understand the geometry behind the scores
- [Domain Calibration](../guides/domain-calibration.md) --- what calibration does, and what it does not fix
- [RAG Verification](../guides/rag-verification.md) --- integrate SGI into your RAG pipeline
