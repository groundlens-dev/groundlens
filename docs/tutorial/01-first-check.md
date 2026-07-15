# Part 1: Your first check

In this part you install groundlens and run a single check against a source document. By the end you will be able to read a result and say, in plain language, what it means.

## Install

```bash
pip install groundlens
```

That is the whole install. No API key, no GPU, no configuration.

## The scenario

You asked a model a question and gave it a document to answer from. You have three strings: the **question**, the **source** you provided, and the **answer** the model returned. You want to know one thing: did the answer actually use the source, or did it drift back to the question and improvise?

That question, "did the answer engage its source", is what the Semantic Grounding Index (SGI) measures.

## Run it

Create a file called `check.py`:

```python
from groundlens import compute_sgi

question = "What does the water damage policy cover?"
source = (
    "Coverage includes burst pipes and sudden appliance failure up to "
    "$50,000. Flood damage requires a separate NFIP policy. "
    "Deductible is $1,500 per occurrence."
)
answer = (
    "The policy covers burst pipes and sudden appliance failure up to "
    "$50,000 per occurrence, with a $1,500 deductible."
)

result = compute_sgi(question=question, context=source, response=answer)

print(f"score:      {result.value:.3f}")
print(f"flagged:    {result.flagged}")
print(f"to source:  {result.ctx_dist:.3f}")
print(f"to question:{result.q_dist:.3f}")
```

Run it:

```bash
python check.py
```

The first run downloads the embedding model. After that it is instant. You will see a score comfortably above 1.0 and `flagged: False`. The answer sits closer to the source than to the question, which is what a grounded answer does.

## Read the result

`compute_sgi` returns an `SGIResult`. The fields you will use most:

- **`value`** is the raw score: `distance(answer, question) / distance(answer, source)`. Above 1.0 means the answer moved toward the source.
- **`flagged`** is the library's own call on whether this needs a human. It is `True` when the score falls into the review or risk band.
- **`ctx_dist`** and **`q_dist`** are the two distances the ratio is built from, exposed so you can see the geometry, not just the verdict.

The thresholds behind `flagged`:

| SGI value | Meaning |
|---|---|
| above 1.20 | Strong engagement with the source. Pass. |
| 0.95 to 1.20 | Partial. Some source influence, not decisive. Review. |
| below 0.95 | Weak. The answer may have ignored the source. Flag. |

## Turn the number into words

The raw score is for pipelines. For something a person can act on, pass the result to `check()`:

```python
from groundlens import compute_sgi, check

result = compute_sgi(question=question, context=source, response=answer)
verdict = check(result)

print(verdict.render())
```

`check()` returns a `Check` with a plain `label` ("Supported by the document"), a one-line `message`, a `level` (`ok`, `review`, or `risk`), and two fields you will rely on in [Part 3](03-a-verification-loop.md): `escalate` and `handoff`. `render()` prints all of it, including the handoff line.

This `check()` function is the single source of truth for wording across the whole project. The README, the [MCP servers](https://github.com/groundlens-dev/groundlens-mcp), and the hosted API all render from it, so what you read here is exactly what your users will read.

## What you have

You ran a deterministic grounding check and read it two ways: as a number for code, and as a sentence for a person. Run it again. The score is identical, every time, on any machine. That determinism is the property the whole design rests on.

There is a question you should be asking: what happens when the answer is drawn from the source but a fact inside it is wrong? That is [Part 2](02-the-blind-spot.md), and it is the most important part of this tutorial.
