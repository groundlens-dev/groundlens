# Groundlens

**Check whether an LLM's answer actually came from its source. Fast, deterministic, no second LLM.**

An LLM answers confidently whether or not it used the document you gave it. Sometimes it draws on the source; sometimes it answers from memory, or drifts to the topic of the question. You cannot tell which by reading the answer, and re-reading every answer by hand, or paying a second LLM to judge each one, does not scale.

Groundlens measures the *geometry* of an answer, where it sits relative to its source and to the question, and turns that into a plain reading: **did this answer come from the source, or not?** It runs in milliseconds, returns the same result every time, and uses no second language model. Its job is to let the clearly grounded answers through and flag the ones worth a closer look, so the slow and expensive checks run only where they are needed.

!!! warning "Groundlens does not measure truth"
    It measures grounding: whether an answer came from its source (SGI) or moves like a well grounded answer (DGI). A statement that is factually wrong but well grounded in the source can pass, and a true statement that ignores the source can be flagged. For truth you need a source of truth: a lookup, a knowledge base, a rule, or a person. Groundlens tells you which answers to send there.

## The pipeline

Checking an LLM's output is a pipeline, cheapest step first. Groundlens is the front of it and decides what reaches the expensive back.

| # | Step | The question it answers | In Groundlens |
|---|---|---|---|
| 1 | **Geometry** (SGI / DGI) | Did the answer come from its source, or drift off it? | Yes |
| 2 | **Consistency** | With no source to compare against, does the model agree with itself? | Yes |
| 3 | **Rules** | Did the answer break a policy, invent a number, skip a disclosure? | Yes |
| 4 | **LLM as judge** | The hard cases that need real reasoning over the evidence. | No |
| 5 | **Human review** | The last step of the pipeline. | No |

Groundlens covers steps 1 to 3 and needs no second LLM. Steps 4 and 5 run only on what the earlier steps flag.

## The four checks

- **[SGI](concepts/sgi.md)**, did the answer come from its source? Use it when you have the retrieved document (a RAG pipeline).
- **[DGI](concepts/dgi.md)**, check an answer when there is no source. It works from the question and the answer alone, comparing the direction the answer takes with how grounded answers usually move.
- **[Consistency](guides/second-stage.md)**, does the model agree with itself? The second stage you escalate to when geometry cannot settle a case.
- **[Rules](adr/0001-rule-set-architecture.md)**, did the answer break a specific policy? Named checks that catch invented figures, missing disclosures, and out-of-remit claims.

## Install

```bash
pip install groundlens
```

The default encoder is `sentence-transformers/sentence-t5-large` (768-dimensional). `import groundlens` stays lightweight and never loads a second language model; the optional model-based second stage is installed separately with `pip install "groundlens[verify]"`.

## A first reading

```python
from groundlens import compute_sgi, check

question = "What is the daily transfer limit?"
context  = "The daily transfer limit is 1,000 EUR per day."
response = "The daily limit is 500 EUR per transaction."   # not in the source

print(check(compute_sgi(question=question, context=context, response=response)).render())
# CHECK: ... (Semantic Grounding Index - SGI=...)
```

Read the **level** (`"ok"`, `"review"`, `"risk"`), not the raw decimal. The number depends on the encoder, so treat it as a relative signal and set the operating point by [calibrating on your own data](concepts/calibration.md).

## Where to go next

- New here: [Installation](getting-started/installation.md) and [Quickstart](getting-started/quickstart.md).
- Understand the method: [How it works](concepts/how-it-works.md), [SGI](concepts/sgi.md), [DGI](concepts/dgi.md), [Calibration](concepts/calibration.md).
- Escalate the hard cases: [Second stage](guides/second-stage.md) and the provider adapters for [OpenAI](providers/openai.md), [Anthropic](providers/anthropic.md), [Google](providers/google.md).
- Privacy: [Data handling](guides/data-handling.md).
- Compliance: [EU AI Act](guides/eu-ai-act.md), [SR 11-7](guides/sr-11-7.md), [NIST AI RMF](guides/nist-ai-rmf.md).
- Editor / chat integration: the [Groundlens MCP server](https://github.com/groundlens-dev/groundlens-mcp).

## Research

The methods are documented in three preprints:

- *Semantic Grounding Index: geometric bounds on context engagement in RAG systems* (2025), [arXiv:2512.13771](https://arxiv.org/abs/2512.13771)
- *A Geometric Taxonomy of Hallucinations in LLMs* (2026), [arXiv:2602.13224](https://arxiv.org/abs/2602.13224)
- *How Transformers Reject Wrong Answers* (2026), [arXiv:2603.13259](https://arxiv.org/abs/2603.13259)
