# Part 2: The blind spot

Most libraries hide their failure cases. This tutorial hands you one on purpose, because using groundlens safely depends on understanding exactly where it stops working. Skip this part and you will misuse the tool.

## Make it fail

Go back to the example from [Part 1](01-first-check.md). The source said the deductible is **$1,500**. Change the answer to say **$2,500**, and change nothing else. Every other word stays identical to a correct, grounded answer.

```python
from groundlens import compute_sgi, check

question = "What does the water damage policy cover?"
source = (
    "Coverage includes burst pipes and sudden appliance failure up to "
    "$50,000. Flood damage requires a separate NFIP policy. "
    "Deductible is $1,500 per occurrence."
)
# One wrong number. Everything else copied from a correct answer.
answer = (
    "The policy covers burst pipes and sudden appliance failure up to "
    "$50,000 per occurrence, with a $2,500 deductible."
)

result = compute_sgi(question=question, context=source, response=answer)
print(check(result).render())
```

Run it. The check **passes**. The answer is reported as supported by the document.

It is not a bug. The answer *is* drawn from the document. It uses the document's vocabulary, its structure, its framing. Geometrically, a wrong number in the right place sits in almost exactly the same location as the right number. The check measures whether the answer engaged its source. It does not, and cannot, measure whether the facts inside it are true.

## Why this happens, briefly

groundlens scores a response by where it sits in embedding space relative to the question and the source. A confabulation that stays *in register*, same topic, same terminology, same shape as a correct answer, lands in the same region. As an error becomes more in-register, every detector of this kind declines toward chance. This is measured, not hypothetical, and it has a name: the register wall. The [Theory](../theory/confabulation-boundary.md) section derives it; the [Benchmarks](../benchmarks/results.md) quantify it.

The one-line version: **grounding is not fact-checking.** A plausible wrong fact in the right frame passes this check by design.

## Why the handoff exists

Look at what `render()` printed under the verdict. Even on a pass, there is a line like:

> Grounding, not facts: a plausible wrong fact in the right frame would pass this check. Verify facts in a second stage.

That is the `handoff` field, and it is not decoration. It is the library telling you, in the result itself, that a pass is not a guarantee of truth. Never drop it when you show a result to a user, and never report a passing check as "verified" or "not hallucinated".

```python
result = compute_sgi(question=question, context=source, response=answer)
verdict = check(result)

print("label:   ", verdict.label)
print("level:   ", verdict.level)      # "ok" here, even though the fact is wrong
print("escalate:", verdict.escalate)
print("handoff: ", verdict.handoff)
```

## What to do with this

You do not fix the blind spot by tuning a threshold or calibrating harder. It is a property of the whole class of embedding-similarity methods, and it does not move. You handle it by architecture: run this cheap check first on everything, and send the cases it cannot settle to a more expensive stage that *reads* the answer against the source. Entailment models, a source lookup, or a judge all do that, and they do not decline in register.

That escalation is what you build in [Part 3](03-a-verification-loop.md).
