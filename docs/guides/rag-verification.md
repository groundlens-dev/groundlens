# RAG Verification

This guide shows how to integrate groundlens SGI scoring into a Retrieval-Augmented Generation (RAG) pipeline to verify that the LLM actually used the retrieved context when generating its response.

## The Problem

In a RAG pipeline, you retrieve relevant documents and pass them as context to the LLM. But retrieval does not guarantee usage --- the LLM may:

1. **Ignore the context** and answer from parametric memory (potentially outdated or wrong)
2. **Partially use the context** and fill gaps with fabricated details
3. **Hallucinate attribution** ("According to the document...") while inventing content

SGI detects case 1 with high confidence, provides signal for case 2, and is robust against case 3 when the fabricated content is distributionally different from the source.

## Basic Integration

```python
from groundlens import compute_sgi


def rag_pipeline(question: str, retriever, llm) -> dict:
    """RAG pipeline with groundlens verification."""
    # Step 1: Retrieve context
    context = retriever.retrieve(question)

    # Step 2: Generate response
    response = llm.generate(question, context=context)

    # Step 3: Verify grounding with SGI
    result = compute_sgi(
        question=question,
        context=context,
        response=response,
    )

    return {
        "response": response,
        "context": context,
        "sgi_score": result.value,
        "sgi_flagged": result.flagged,
        "sgi_explanation": result.explanation,
    }
```

## Decision Logic

Use the SGI score to implement a verification policy:

```python
from groundlens import compute_sgi


def verified_rag(question, context, response):
    """RAG with three-tier verification."""
    result = compute_sgi(
        question=question,
        context=context,
        response=response,
    )

    if result.value >= 1.20:
        # Strong pass: high confidence in context engagement
        return {"response": response, "confidence": "high", "action": "serve"}

    elif result.value >= 0.95:
        # Partial engagement: response may have mixed sources
        return {"response": response, "confidence": "medium", "action": "review"}

    else:
        # Flagged: response likely ignores context
        return {
            "response": response,
            "confidence": "low",
            "action": "regenerate_or_escalate",
        }
```

## Multi-Chunk RAG

When your retriever returns multiple chunks, you have several options for SGI evaluation:

### Option 1: Concatenate Chunks

```python
chunks = retriever.retrieve(question, top_k=3)
combined_context = "\n\n".join(chunks)

result = compute_sgi(
    question=question,
    context=combined_context,
    response=response,
)
```

### Option 2: Score Against Each Chunk

```python
from groundlens import compute_sgi

chunks = retriever.retrieve(question, top_k=3)

chunk_scores = []
for chunk in chunks:
    result = compute_sgi(
        question=question,
        context=chunk,
        response=response,
    )
    chunk_scores.append(result)

# Use the best chunk score (the response may engage with only one chunk)
best = max(chunk_scores, key=lambda r: r.value)
print(f"Best SGI: {best.value:.3f} (flagged: {best.flagged})")
```

!!! tip "When to use which"
    **Concatenation** is simpler and works well when chunks are topically coherent. **Per-chunk scoring** is better when chunks cover different aspects of the question --- it avoids penalizing a response that correctly focuses on the most relevant chunk.

## Async RAG Pipeline

For production systems handling concurrent requests:

```python
import asyncio
from groundlens import compute_sgi


async def async_rag(question, retriever, llm):
    # Run retrieval and keep the context
    context = await retriever.aretrieve(question)
    response = await llm.agenerate(question, context=context)

    # SGI is CPU-bound (embedding inference), run in executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: compute_sgi(
            question=question,
            context=context,
            response=response,
        ),
    )

    return {
        "response": response,
        "sgi": result.value,
        "flagged": result.flagged,
    }
```

## Monitoring Dashboard

Track SGI scores over time to monitor RAG quality:

```python
import json
import logging

logger = logging.getLogger("rag_monitor")


def log_sgi_metrics(question, context, response, result):
    """Log SGI metrics for monitoring."""
    metrics = {
        "question_length": len(question),
        "context_length": len(context),
        "response_length": len(response),
        "sgi_value": result.value,
        "sgi_normalized": result.normalized,
        "sgi_flagged": result.flagged,
        "q_dist": result.q_dist,
        "ctx_dist": result.ctx_dist,
    }
    logger.info("sgi_metric %s", json.dumps(metrics))
```

Key metrics to track:

| Metric | What it tells you |
|---|---|
| Mean SGI over time | Overall RAG grounding quality |
| Flagged rate | Percentage of responses needing review |
| SGI by retriever configuration | Which retrieval settings produce best grounding |
| SGI vs. response length | Whether longer responses lose grounding |

## Fallback Strategies

When SGI flags a response:

```python
def rag_with_fallback(question, retriever, llm, max_retries=2):
    """Retry generation when SGI flags the response."""
    context = retriever.retrieve(question)

    for attempt in range(max_retries + 1):
        response = llm.generate(question, context=context)
        result = compute_sgi(
            question=question,
            context=context,
            response=response,
        )

        if not result.flagged:
            return {"response": response, "attempts": attempt + 1}

    # All attempts flagged --- return with warning
    return {
        "response": response,
        "attempts": max_retries + 1,
        "warning": "Response flagged after all retry attempts. Human review recommended.",
    }
```

!!! warning "Retry limits"
    Set a reasonable retry limit. If the LLM consistently produces flagged responses for a given question/context pair, the issue may be with the retrieval quality (irrelevant context) rather than the generation.
