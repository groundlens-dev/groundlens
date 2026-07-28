# GroundingSwitch

**Stage 2 of the verification pipeline.** Converts a geometric score (SGI or DGI) into a control decision: may this response be written into agent or RAG state, or would that contaminate the next turn?

Geometry answers *"did the answer come from the source?"*. The Switch answers *"what should the system do with that signal?"*.

```
01 Geometry      SGI / DGI          (deterministic, no model)
02 Switch        THIS PAGE         (deterministic, no model)
03 Consistency   resample          (small open model)
04 Rules         policy checks     (deterministic)
05 LLM-as-judge
06 Human review
```

## Why it exists

In long-running agents and RAG pipelines the *context* — conversation history, retrieved documents, previous model outputs, compacted summaries — can dominate the model's parametric memory. When that context is contaminated (a prior hallucination, a bad retrieval, a degraded compaction), the model tends to **propagate the error** into the next turn.

Geometry (SGI/DGI) already detects the misalignment. Without a control layer, that detection is only a score in a log. The Switch turns the score into an **action** that prevents the bad answer from entering the next turn's state.

Typical failure modes the Switch is designed for:

| Failure mode | What happens without the Switch |
|---|---|
| Contaminated RAG retrieval | A wrong chunk is retrieved; the model answers from it; the answer is written back into history and poisons later turns. |
| Agent self-contamination | An earlier hallucinated tool result or message stays in the agent state; later steps treat it as fact. |
| Compaction drift | A long conversation is compacted; the summary drops a constraint or invents one; subsequent answers inherit the error. |
| Fluent off-source answer | SGI/DGI flags the answer, but the pipeline still appends it to the transcript because nothing consumes the flag. |

The Switch does not invent new geometric signal. It makes the existing signal **operational**.

## What it does not do

- It does **not** measure truth. Like SGI/DGI, it measures grounding geometry and turns that into routing.
- It does **not** call a model. Importing and running the Switch never loads embeddings or LLMs beyond what geometry already used.
- It does **not** replace Consistency or Rules. Ambiguous geometry still escalates; policy violations still need Stage 4.
- It does **not** rewrite the answer. Recovery (`fallback`, `regenerate`) is the caller's responsibility.

## Actions

| Action | `write_to_state` | Meaning | Typical next step |
|--------|------------------|---------|-------------------|
| `accept` | `True` | Clearly grounded. Safe to keep. | Append to history / return to user. |
| `reject` | `False` | Clearly ungrounded. Drop it. | Return an error or a canned refusal. |
| `fallback` | `False` | Ungrounded; context is the likely cause. | Discard or down-weight retrieved context; answer from parametric knowledge or a clean source. |
| `regenerate` | `False` | Ungrounded; try again. | Re-ask the model, optionally with less context or a stricter prompt. |
| `escalate` | `False` | Geometry is ambiguous. | Continue to Consistency / Rules / LLM-as-judge. |

`write_to_state` is `True` **only** for `accept`. Every other action refuses to put the response into the next turn's context.

### Choosing `on_reject`

The constructor argument `on_reject` sets what happens when geometry is clearly negative. Allowed values: `fallback`, `reject`, `regenerate`, `escalate`. Default: **`fallback`**.

| `on_reject` | When to use it |
|---|---|
| `fallback` (default) | Contaminated context is the main risk. You prefer to answer without the bad retrieval rather than fail hard. |
| `reject` | Strict pipelines where any ungrounded answer must not reach the user. |
| `regenerate` | You have budget to re-sample and the model often recovers on a second try. |
| `escalate` | You always want Consistency / a judge on negative geometry, never an automatic recovery. |

`accept` is **not** a valid `on_reject` value.

## Decision rules

Thresholds are the same calibrated constants used by `check()`.

### SGI (three zones)

| Score | Action |
|---|---|
| `≥ 1.20` (`SGI_STRONG_PASS`) | `accept` |
| `< 0.95` (`SGI_REVIEW`) | `on_reject` (default `fallback`) |
| in `[0.95, 1.20)` | `escalate` |

### DGI (binary)

DGI has no middle band in the current calibration.

| Score | Action |
|---|---|
| `≥ 0.525` (`DGI_PASS`) | `accept` |
| `< 0.525` | `on_reject` |

### Non-geometric inputs

If you pass a Consistency `Check` (method like `selfcheck_nli`), the Switch does not reinterpret it. It returns `escalate` and leaves the decision to later stages.

## API

### Construction

```python
from groundlens import GroundingSwitch

switch = GroundingSwitch()  # defaults: SGI 1.20 / 0.95, DGI 0.525, on_reject="fallback"

switch = GroundingSwitch(
    accept_threshold_sgi=1.20,
    reject_threshold_sgi=0.95,
    accept_threshold_dgi=0.525,
    on_reject="fallback",  # or "reject" | "regenerate" | "escalate"
)
```

Raises `ValueError` if `reject_threshold_sgi > accept_threshold_sgi` or if `on_reject` is invalid.

### `decide` / `__call__`

```python
decision = switch.decide(sgi_or_dgi)  # or switch(sgi_or_dgi)
```

Accepted input types:

- `SGIResult`
- `DGIResult`
- `GroundlensScore`
- `Check`

Returns a frozen `SwitchDecision`:

| Field | Type | Meaning |
|---|---|---|
| `action` | `SwitchAction` | The control action. |
| `write_to_state` | `bool` | Whether it is safe to write the response into agent/RAG state. |
| `reason` | `str` | Short plain-language explanation. |
| `check` | `Check` | The canonical geometric check for the underlying score. |
| `score` | `float` | Raw geometric value. |
| `method` | `str` | `"sgi"` or `"dgi"` (or the non-geometric method if escalated). |
| `level` | `str` | `"ok"` / `"review"` / `"risk"` from the Check. |

`SwitchAction` is a `str` Enum (`"accept"`, `"reject"`, `"fallback"`, `"regenerate"`, `"escalate"`), so it serialises cleanly in logs and JSON.

## Usage patterns

### RAG path (SGI → Switch)

```python
from groundlens import compute_sgi, GroundingSwitch, SwitchAction

switch = GroundingSwitch()
sgi = compute_sgi(question=question, context=retrieved, response=answer)
decision = switch.decide(sgi)

if decision.write_to_state:
    history.append(answer)
    return answer
elif decision.action is SwitchAction.FALLBACK:
    # Bad retrieval is the likely cause. Answer without this context.
    return answer_without_context(question)
elif decision.action is SwitchAction.ESCALATE:
    return run_consistency_or_judge(question, answer, retrieved)
else:
    return refuse(decision.reason)
```

### Agent loop (protect state)

```python
state: list[str] = []
switch = GroundingSwitch(on_reject="fallback")

for turn in conversation:
    answer = agent.step(turn, state=state)
    score = compute_sgi(question=turn.question, context=turn.context, response=answer)
    decision = switch.decide(score)

    if decision.write_to_state:
        state.append(answer)
    elif decision.action is SwitchAction.FALLBACK:
        # Do not append. Optionally strip turn.context for the next attempt.
        ...
    elif decision.action is SwitchAction.ESCALATE:
        # Hand off to Consistency / human; still do not append until resolved.
        ...
```

The invariant: **nothing enters `state` unless `write_to_state` is True.**

### No-source path (DGI → Switch)

```python
from groundlens import compute_dgi, GroundingSwitch

switch = GroundingSwitch(on_reject="escalate")
dgi = compute_dgi(question=question, response=answer)
decision = switch.decide(dgi)

if decision.write_to_state:
    return answer
# DGI is binary: no middle band. Negative geometry goes straight to on_reject.
return run_consistency(question, answer)
```

### Custom thresholds

If you calibrated SGI/DGI on your domain with `fit_thresholds`, pass the same cuts into the Switch so routing and `check()` agree:

```python
switch = GroundingSwitch(
    accept_threshold_sgi=fit.sgi_strong_pass,
    reject_threshold_sgi=fit.sgi_review,
    accept_threshold_dgi=fit.dgi_pass,
)
```

## Relationship to `check()`

| Object | Role |
|---|---|
| `check(score)` | Human-readable verdict (`ok` / `review` / `risk`) and audit text. |
| `GroundingSwitch.decide(score)` | Machine-readable **control action** for state and routing. |

They share thresholds. Use both: log `check(...).render()` for the trail; branch on `decision.action` / `decision.write_to_state` for control flow.

## Cost and dependencies

- **No model dependency.** The Switch is pure Python over scores you already computed.
- **No network.** Nothing is sent anywhere.
- **Latency.** Microseconds after geometry has finished.

It stays in the deterministic core of Groundlens. `import groundlens` does not load the Switch's logic with any encoder or LLM.

## Worked example

```python
from groundlens import compute_sgi, check, GroundingSwitch, SwitchAction

question = (
    "A user of our cloud backup service wants to understand the data retention "
    "rules for the Business plan: how long deleted files can still be recovered."
)
context = (
    "On the Business plan, deleted files are moved to a recovery area and can be "
    "restored for 90 days from the date of deletion; after 90 days they are "
    "permanently purged and cannot be recovered."
)
answer_grounded = (
    "On the Business plan you can restore a deleted file for 90 days after it was "
    "deleted; once those 90 days pass it is purged for good."
)
answer_ungrounded = (
    "Deleted files on the Business plan are kept forever and can always be "
    "restored at any time, so there is no purge window to worry about."
)

switch = GroundingSwitch()

for label, answer in (("grounded", answer_grounded), ("ungrounded", answer_ungrounded)):
    sgi = compute_sgi(question=question, context=context, response=answer)
    decision = switch.decide(sgi)
    print(label, check(sgi).label, "->", decision.action.value, "write=", decision.write_to_state)
```

Expected shape of the output:

```text
grounded    Supported by the document -> accept   write= True
ungrounded  ...                       -> fallback write= False
```

(Exact SGI labels depend on the encoder; the Switch action follows the thresholds above.)

## See also

- [SGI](sgi.md) — geometric score when context is present
- [DGI](dgi.md) — geometric score when context is absent
- [How it works](how-it-works.md) — pipeline overview
- [Second stage](../guides/second-stage.md) — Consistency after `escalate`
- Example script: [`examples/grounding_switch.py`](https://github.com/groundlens-dev/groundlens/blob/main/examples/grounding_switch.py)
