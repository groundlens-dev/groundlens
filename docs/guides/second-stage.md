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

## The methods

Two presets, both returning a `Check`:

- **`SelfCheckNLI`** resamples the model and scores contradiction with NLI. This reproduces SelfCheckGPT-NLI, the validated method (92.50 AUC-PR on WikiBio-GPT3, Manakul et al., EMNLP 2023).
- **`ParaphraseCheck`** rewords the question and answers each rewording. It front-loads the signal, reaching good detection at a low sample budget, but saturates, since a question has only so many genuinely different phrasings.

```python
from groundlens.verify import SelfCheckNLI

checker = SelfCheckNLI(model="Qwen/Qwen2.5-7B-Instruct", n_samples=7)
reading = checker.check("What is the capital of Spain?", "Madrid")
reading.level        # "ok" / "review" / "risk"
```

Use `checker.verify(...)` instead of `checker.check(...)` to get the full `Verification`: the `Check` plus the samples, the consistency score, the seed, and the wall-clock time. A stochastic stage inside an auditable library should leave that trail.

## Any model, not just Hugging Face

The detector depends only on a small `TextGenerator` protocol (`generate(prompt, n)` and `generate_many(prompts)`). The bundled `HFTextGenerator` is the local, batched default; to use an API model, wrap your client in an object with those two methods and pass it as `generator=...`. Pick the scorer with `scorer="nli"` (validated, needs the extra) or `scorer="embedding"` (reuses the core sentence encoder, no extra needed).

## Calibration

The second-stage cut-points (`SC_CONSISTENT`, `SC_MIXED`) are provisional. Unlike the SGI and DGI thresholds they are not calibrated against a labeled benchmark. Calibrate them on your own data with [`fit_thresholds`](../concepts/calibration.md) before relying on the level in production.

## What it does not do

Consistency is not truth. A model can be confidently and consistently wrong, and the second stage will read that as consistent. For high-stakes factual claims, a consistent reading still warrants a source check or a human. The model-based stage narrows the residue the first stage escalates; it does not eliminate it.
