# Tutorial

This tutorial walks you from an empty file to a working grounding check that knows its own limits. You will not just call the library. You will see, with your own eyes, the one case it cannot handle, and you will learn why that case is the whole point of the design.

By the end you will have built a small verification loop: a function that takes a question, a source, and an answer, decides whether the answer was drawn from the source, and escalates the cases geometry cannot settle.

It is written to be read in order. Each part builds on the last, and every code block runs as written.

## What you will build

A three-stage check over a tiny retrieval-augmented pipeline:

1. A first-stage grounding check that runs on every answer, deterministically, in milliseconds.
2. A demonstration of its characterized blind spot, so you never trust it beyond what it can do.
3. An escalation path that hands the hard cases to a second stage.

## Before you start

You need Python 3.10 or newer. That is the only requirement. The first `compute_dgi` or `compute_sgi` call downloads a small sentence-transformer model (about 90 MB) and caches it; everything after that is offline and local.

## The parts

1. [Your first check](01-first-check.md) — install groundlens and read a real result.
2. [The blind spot](02-the-blind-spot.md) — make the check fail on purpose, and understand why.
3. [A verification loop](03-a-verification-loop.md) — wire it into a pipeline that escalates what it cannot resolve.

When you finish, the [How-to guides](../guides/rag-verification.md) show how to take this into production, the [API reference](../api/index.md) documents every parameter, and the [Theory](../theory/hallucination-taxonomy.md) section explains the geometry underneath.

Start with [Part 1](01-first-check.md).
