# GroundingSwitch

**Stage 2 of the verification pipeline.** Converts a geometric score into a decision about whether a response may be written into agent or RAG state.

## Why it exists

In long-running agents and RAG pipelines the *context* (conversation history, retrieved documents, previous model outputs) can dominate the model's parametric memory. When that context is contaminated — a prior hallucination, a bad retrieval, a degraded compaction — the model tends to propagate the error.

Geometry (SGI/DGI) already detects the misalignment. The Switch turns that signal into an **action** that prevents the bad answer from entering the next turn's context.

```
01 Geometry      SGI / DGI
02 Switch        ← this page
03 Consistency   resample
04 Rules         policy checks
05 LLM-as-judge
06 Human review
```

## Actions

| Action | `write_to_state` | Meaning |
|--------|------------------|--------|
| `accept` | `True` | Clearly grounded. Safe to write into state. |
| `reject` | `False` | Clearly ungrounded. Drop the response. |
| `fallback` | `False` | Ungrounded. Discard context influence / fall back to parametric knowledge. |
| `regenerate` | `False` | Ungrounded. Ask the model again (optionally with less context weight). |
| `escalate` | `False` | Geometry is ambiguous. Continue to Consistency. |

Default `on_reject` is `fallback` — the most common failure mode is contaminated context dominating the answer.

## Decision rules

**SGI (three zones)**

- `≥ 1.20` → `accept`
- `< 0.95` → `on_reject` (default `fallback`)
- in between → `escalate`

**DGI (binary)**

- `≥ 0.525` → `accept`
- `< 0.525` → `on_reject`

Thresholds are the same calibrated constants used by `check()`.

## Usage

```python
from groundlens import compute_sgi, GroundingSwitch, SwitchAction

switch = GroundingSwitch()  # on_reject="fallback" by default
sgi = compute_sgi(question=q, context=ctx, response=answer)
decision = switch.decide(sgi)

if decision.write_to_state:
    state.append(answer)
elif decision.action is SwitchAction.FALLBACK:
    # discard retrieved context; re-ask or use parametric path
    ...
elif decision.action is SwitchAction.ESCALATE:
    # continue to Consistency / LLM-as-judge
    ...
```

The Switch accepts `SGIResult`, `DGIResult`, `GroundlensScore`, or an already-built `Check`. It has **no model dependency** and stays in the deterministic core.

## See also

- [SGI](sgi.md)
- [DGI](dgi.md)
- [How it works](how-it-works.md)
- Example: [`examples/grounding_switch.py`](https://github.com/groundlens-dev/groundlens/blob/main/examples/grounding_switch.py)
