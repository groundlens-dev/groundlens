# Second stage (model-based)

Groundlens is the deterministic first stage. It clears the clearly grounded, catches the clearly ungrounded, and escalates what geometry cannot settle. `groundlens.verify` is the stage you escalate to: a model-based consistency check that ships in the same library and returns the same [`Check`](../concepts/how-it-works.md).

It is optional and kept out of the core import path. `import groundlens` never loads a model, and even `import groundlens.verify` loads nothing heavy until a detector actually runs.

## Install

```bash
pip install "groundlens[verify]"
```

This pulls in `transformers`, `torch` and `accelerate`. On Linux it also installs `bitsandbytes` for 4-bit loading; on macOS load models with `load_in_4bit=False`.

## The pipeline

Run the deterministic stage first and only spend model calls on escalated cases:

```python
from groundlens.verify import two_stage

result = two_stage(
    question="What is the capital of Spain?",
    answer="Madrid",
    context="Spain is a country in Europe. Its capital is Madrid.",
    model="Qwen/Qwen2.5-7B-Instruct",
)
result.escalated   # False: SGI settled it, no model call
result.stage1      # the deterministic Check
result.stage2      # None here (only set when stage 2 runs)
result.final       # the Check to act on
```

When stage one escalates (its `Check.escalate` is set), `two_stage` runs the model-based detector and `result.final` becomes the stage-two reading.

## The two consistency methods

The second stage reads consistency. It perturbs either the model or the input, generates more than once, and measures whether the readings agree. Low agreement means the model disagrees with itself, which reads as risk. Both methods return a consistency score in [0, 1] and a `Check`.

- **`SampleConsistency`** resamples the same question several times with sampling on. The variation comes from the model's own randomness, so it needs several samples before the signal is stable.
- **`ParaphraseCheck`** rewords the question and answers each rewording once. The variation comes from the input rather than from sampling, so it reaches a useful signal at a lower sample budget. It saturates, since a question has only so many genuinely different phrasings.

```python
from groundlens.verify import ParaphraseCheck

checker = ParaphraseCheck(model="Qwen/Qwen2.5-7B-Instruct", n_samples=7)
reading = checker.check("What is the capital of Spain?", "Madrid")
reading.level        # "ok" / "review" / "risk"
```

`SampleConsistency` has the same shape and reads the model's own randomness instead:

```python
from groundlens.verify import SampleConsistency

checker = SampleConsistency(model="Qwen/Qwen2.5-7B-Instruct", n_samples=10)
reading = checker.check("What is the capital of Spain?", "Madrid")
```

Use `checker.verify(...)` instead of `checker.check(...)` to get the full `Verification`: the `Check` plus the samples, the consistency score, the seed, and the wall-clock time. A stochastic stage inside an auditable library should leave that trail.

## Any model, not just Hugging Face

The detector depends only on a small `TextGenerator` protocol (`generate(prompt, n)` and `generate_many(prompts)`). The bundled `HFTextGenerator` is the local, batched default; to use an API model, wrap your client in an object with those two methods and pass it as `generator=...`. Pick the scorer with `scorer="nli"` (entailment, needs `groundlens[verify]`) or `scorer="embedding"` (reuses the core sentence encoder, torch-free, no extra needed).

## Using an API provider

The second stage runs against a local Hugging Face model by default, but you can point it at a hosted API instead. Three adapters ship with the library:

| Adapter | Default model | Install |
|---|---|---|
| `AnthropicGenerator` | `claude-3-5-haiku-latest` | `pip install "groundlens[anthropic]"` |
| `OpenAIGenerator` | `gpt-4o-mini` | `pip install "groundlens[openai]"` |
| `GeminiGenerator` | `gemini-1.5-flash` | `pip install "groundlens[google]"` |

`OpenAIGenerator` also accepts a `base_url`, so it drives any OpenAI-compatible endpoint.

```python
from groundlens.verify import ParaphraseCheck, AnthropicGenerator

checker = ParaphraseCheck(generator=AnthropicGenerator())
reading = checker.check("What is the capital of Spain?", "Madrid")
```

!!! warning "Where your data goes"
    With a local model the second stage sends nothing out. With an API adapter, your prompt and the answer go to that provider under your own key and their terms. groundlens holds no key of its own and has no server in the path. See [Data Handling and Privacy](data-handling.md).

## Calibration

The second-stage cut-points (`SC_CONSISTENT`, `SC_MIXED`) are provisional. Unlike the SGI and DGI thresholds they are not calibrated against a labeled benchmark. Calibrate them on your own data with [`fit_thresholds`](../concepts/calibration.md) before relying on the level in production.

## What it does not do

Consistency is not truth. A model can be confidently and consistently wrong, and the second stage will read that as consistent. For high-stakes factual claims, a consistent reading still warrants a source check or a human. The model-based stage narrows the residue the first stage escalates; it does not eliminate it.
