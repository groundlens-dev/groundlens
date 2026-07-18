# Custom encoders / running without torch

groundlens defaults to loading a `sentence-transformers` model
(`Snowflake/snowflake-arctic-embed-l-v2.0`) on first use. You can override
this entirely by supplying **your own embedding function**. This lets you:

- bring an encoder groundlens does not load itself (a hosted embedding API,
  a quantized local model, an in-house model);
- reuse **precomputed embeddings** without re-encoding;
- run SGI/DGI **without installing torch** — the custom-encoder path never
  imports `sentence-transformers`.

## The encoder contract

An encoder is *a callable taking `list[str]` and returning an `(n, d)`
array* (numpy or array-like; it is coerced to `float32`). The type alias
`groundlens.EmbeddingFn` captures this:

```python
EmbeddingFn = Callable[[list[str]], "NDArray[np.float32]"]
```

Two common shapes satisfy it:

```python
# 1. A SentenceTransformer's bound .encode method.
from sentence_transformers import SentenceTransformer
encoder = SentenceTransformer("all-MiniLM-L6-v2").encode

# 2. A plain function (here a hosted embedding API).
import numpy as np

def encoder(texts: list[str]) -> np.ndarray:
    vectors = my_embedding_api.embed(texts)  # returns list[list[float]]
    return np.asarray(vectors, dtype=np.float32)
```

## Per-call injection

Pass `encoder=` to any scoring entry point — `compute_sgi`, `compute_dgi`,
the `SGI` / `DGI` classes, `calibrate`, and `fit_thresholds`:

```python
from groundlens import compute_sgi, compute_dgi, SGI, DGI

compute_sgi(
    question="What is the capital of France?",
    context="France's capital is Paris.",
    response="The capital of France is Paris.",
    encoder=encoder,
)

compute_dgi(
    question="What causes seasons?",
    response="Seasons are caused by Earth's axial tilt.",
    encoder=encoder,
)

# Reusable scorers store the encoder once.
sgi = SGI(encoder=encoder)
dgi = DGI(encoder=encoder)
```

## Process-global injection

If every call in your process uses the same encoder, register it once with
`set_default_encoder`. This works regardless of how scoring functions were
imported (no monkeypatching):

```python
import groundlens

groundlens.set_default_encoder(encoder)

# No encoder= needed anymore; both layers route through it.
groundlens.compute_sgi(question="...", context="...", response="...")
groundlens.compute_dgi(question="...", response="...")

groundlens.set_default_encoder(None)  # restore the default path
```

`groundlens.get_default_encoder()` returns the currently registered callable
(or `None`).

## Precomputed embeddings

If you already have vectors, wrap a lookup in a closure so groundlens never
re-encodes:

```python
import numpy as np

cache = {"What is X?": vec_q, "X is Y.": vec_r}  # text -> np.float32 vector

def precomputed(texts: list[str]) -> np.ndarray:
    return np.vstack([cache[t] for t in texts]).astype(np.float32)

groundlens.compute_dgi(question="What is X?", response="X is Y.", encoder=precomputed)
```

## Running without torch

The custom-encoder path does **not** import `sentence-transformers` (and
therefore not torch). If your encoder is itself torch-free (a hosted API, a
numpy model, or precomputed vectors), you can score with only `numpy`
installed.

!!! warning "Bundled thresholds are encoder-specific"
    The bundled SGI/DGI thresholds and the bundled DGI `mu_hat` are
    calibrated for the **default** encoder. When you supply a custom encoder
    (or a non-default model) while relying on the bundled constants,
    groundlens emits a one-time `UserWarning`. Re-fit your decision
    thresholds with [`fit_thresholds`](../concepts/calibration.md) and your
    DGI reference direction with `calibrate`, both of which accept the same
    `encoder=` argument.

## Next steps

- [Calibration](../concepts/calibration.md) — `fit_thresholds` and
  re-calibrating `mu_hat` for your encoder.
- [Domain Calibration Guide](domain-calibration.md) — end-to-end walkthrough.

## What changes when you bring your own encoder

Three things are worth knowing before you trust the scores.

**The cut-off values were set for the default encoder.** SGI and DGI turn a raw score into a pass or a flag using thresholds, and DGI also uses a learned reference direction (`mu_hat`). Both were fitted on the default model. When you pass a different `encoder=`, the raw geometry still works, but those cut-offs may sit in the wrong place, so the `flagged` field can mislead you. The library prints a one-time warning to remind you. Re-fit with `fit_thresholds(...)` for the cut-offs and `calibrate(...)` for the DGI direction. Until you do, rank on the raw score (`result.value`) instead of trusting the flag.

**If the encoder is a language model, pool by mean.** A sentence encoder already returns one vector per text. A raw language model returns one vector per token, so you have to reduce them to one. Average them (mean pooling). Do not use the last token's vector: in our reasoning benchmark, last-token vectors from base language models scored at or below chance.

**Bigger is not automatically better.** In the same benchmark, an 8B base model did not beat a 1.5B one at grounding. Choose your encoder by measuring it on a small labelled set from your own use case, not by parameter count.

**DGI is more sensitive to the encoder than SGI.** SGI compares distances and degrades gently. DGI depends on a single learned direction, and on raw base-language-model embeddings it fell to chance in our run. If you rely on DGI with a custom encoder, calibrate it and measure it before you ship.
