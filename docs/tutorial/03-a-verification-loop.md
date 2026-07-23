# Part 3: A verification loop

You now know what the check does ([Part 1](01-first-check.md)) and what it cannot do ([Part 2](02-the-blind-spot.md)). In this part you put both together into a small loop: check every answer cheaply, and escalate only the ones geometry cannot resolve. This is the two-stage design the whole library is built around.

## The shape of the loop

Every answer takes one of three paths:

- **Passes cleanly** (`level == "ok"`): return it, with the handoff noted.
- **Falls in the review or risk band** (`escalate == True`): geometry says it cannot settle this. Send it to a second stage.

Here is a complete, runnable loop. The "second stage" is a stub you would replace with an entailment model, a lookup, or a judge. The point is the routing, not the stub.

```python
from groundlens import compute_sgi, check


def second_stage(question: str, source: str, answer: str) -> str:
    """Stand-in for your expensive verifier.

    In production this is an entailment model (NLI), a lookup against the
    source, or an LLM judge. It reads the answer against the source, which is
    exactly what geometry cannot do, and it does not decline in register.
    """
    return "ESCALATED: send to entailment / lookup / judge"


def verify(question: str, source: str, answer: str) -> dict:
    result = compute_sgi(question=question, context=source, response=answer)
    verdict = check(result)

    if verdict.escalate:
        return {
            "decision": "escalated",
            "reason": verdict.message,
            "second_stage": second_stage(question, source, answer),
            "score": round(result.value, 3),
        }

    return {
        "decision": "passed",
        "label": verdict.label,
        "handoff": verdict.handoff,  # a pass is not a truth guarantee
        "score": round(result.value, 3),
    }
```

## Run it on three answers

```python
question = "What does the water damage policy cover?"
source = (
    "Coverage includes burst pipes and sudden appliance failure up to "
    "$50,000. Flood damage requires a separate NFIP policy. "
    "Deductible is $1,500 per occurrence."
)

answers = {
    "grounded and correct":
        "Burst pipes and appliance failure are covered up to $50,000, "
        "with a $1,500 deductible.",
    "ignores the source":
        "Water damage is generally covered by most standard home policies.",
    "in-register, one wrong fact":
        "Burst pipes and appliance failure are covered up to $50,000, "
        "with a $2,500 deductible.",
}

for name, answer in answers.items():
    outcome = verify(question, source, answer)
    print(f"\n{name}")
    print(f"  {outcome}")
```

## Read the three outcomes

- **Grounded and correct** passes. The loop returns it and carries the handoff line forward.
- **Ignores the source** escalates. The answer drifted back to the question, the score drops below the review threshold, and `escalate` is `True`. Geometry caught this one cleanly, because a disengaged answer is out of register.
- **In-register, one wrong fact** passes. This is the case from [Part 2](02-the-blind-spot.md). The loop returns it as passed, with the handoff attached, because geometry cannot see the wrong number. In production, the handoff is your instruction to run a fact-level check on anything that matters, even when it passed.

That third outcome is not a failure of the loop. It is the loop being exactly as honest as the measurement allows: it resolves what it can, on volume, for free, and it never claims to have resolved what it cannot.

## The DGI variant, for when there is no source

Sometimes you have only a question and an answer, no document to check against. Use `compute_dgi`, which reads the geometry of the answer alone. It is a coarser signal with a lower ceiling, so prefer SGI whenever a source exists, but the loop shape is identical:

```python
from groundlens import compute_dgi, check

result = compute_dgi(
    question="What causes seasons on Earth?",
    response="Seasons are caused by Earth's 23.5-degree axial tilt.",
)
verdict = check(result)
print(verdict.render())
```

## Where to go next

You have built the core of a production verifier: a deterministic first stage that triages every answer and escalates the ones it cannot settle. From here:

- [How-to: RAG verification](../guides/rag-verification.md) takes this into a real retrieval pipeline.
- [How-to: Domain calibration](../guides/domain-calibration.md) tunes the escalation rate to your data.
- [How-to: Batch evaluation](../guides/batch-evaluation.md) runs the loop over a dataset.
- [Theory: the confabulation boundary](../theory/confabulation-boundary.md) explains, with the geometry, why the blind spot is where it is.

The single idea to carry out of this tutorial: groundlens is the cheap first stage that tells your expensive second stage what to look at. Its value is not that it is always right. Its value is that it knows, and says, when it cannot be.
