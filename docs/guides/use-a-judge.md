# Use a judge

The exact checks catch a figure that is wrong, recomputed wrongly, taken from
outside the scope, or of another kind than the question asked. They do not
catch a correct-looking figure taken from the wrong row of the right table, or
a sentence that says something the passages never said. For that you need a
model that reads. GroundLens calls it the **judge**.

GroundLens does not ship a model. You pass the client you already use, and
GroundLens sends it one fixed prompt per answer, but only when the exact checks
have not already failed that answer. The judge can escalate and never pass, so
on a FAIL its reply could change nothing: it is not asked, and you do not pay
for the call.

## The short version

```{code-block} python
from openai import OpenAI
import groundlens as gl

policy = """
id: credit_desk
version: 1.0.0
extends: eu_ai_act_high_risk_v1
verifiers:
  forbidden: []
judge:
  required: true
"""

verifier = gl.Verifier(
    policy,
    judge=gl.judges.openai_compatible(OpenAI(), "gpt-4.1"),
    sink=gl.sinks.jsonl("records/"),
)
record = verifier.check(question=q, answer=a, passages=passages, scope={"entity": "UPS"})
```

The shipped policies forbid `llm_judge.*`, so a policy that uses a judge
extends one, empties `verifiers.forbidden` and adds a `judge` section.

## Which clients

| adapter | client | notes |
| --- | --- | --- |
| `gl.judges.openai_compatible(client, model)` | `openai.OpenAI`, or any client with the same chat API | point `base_url` at vLLM, Ollama or your gateway to keep everything on your servers; `json_mode=False` if the server has no `response_format` |
| `gl.judges.azure_openai(client, deployment)` | `openai.AzureOpenAI` | |
| `gl.judges.bedrock(client, model_id)` | `boto3.client("bedrock-runtime")` | Converse API; set the read timeout in the client's config |

Every call uses temperature 0. Anything else with a `complete(system, user)`
method returning `(text, model)` works too.

## What the judge is asked

One prompt per answer, from a fixed template (`groundlens.judge/1`). It
contains what `PASS` means for your application, the scope, the question,
the answer, every passage with its id and provenance, and the sentences of
the answer to label. It does not contain the policy's name or version, so a
reply stays valid when the same input is replayed under a renamed policy. For each sentence the judge answers `supported`,
`unsupported`, `contradicted` or `uncertain`, with the passages it relied on.
A sentence is supported only if a passage about the stated scope says it, or
it follows by simple arithmetic or logic.

See the exact prompt for any input, before you send anything anywhere:

```{code-block} bash
groundlens judge show-template --answer a.txt --source 10k#p114=p114.txt \
  --provenance 10k#p114:entity=UPS --scope entity=UPS
```

## What its labels do

The judge never decides. Its labels are evidence, and the policy's `judge`
section says what they may do:

```{code-block} yaml
judge:
  required: true        # a request checked without a judge goes to REVIEW
  contradicted: REVIEW  # or FAIL
  unsupported: REVIEW   # also covers "uncertain"
```

| the judge says | the sentence gets |
| --- | --- |
| supported | nothing: agreement resolves nothing on its own |
| unsupported or uncertain | `unsupported` (REVIEW by default) |
| contradicted | `contradicted` (REVIEW by default, FAIL if the policy says so) |
| no label, a label outside the four, or a reply that is not the JSON asked for | REVIEW |
| a timeout or an error | REVIEW |
| not asked, because the exact checks already failed the answer | FAIL stays FAIL; a required judge that was not asked adds no reason |

Because the judge's agreement counts for nothing, a judge that is wrong, or
that a passage has talked into saying "supported", cannot pass an answer that
the exact checks fail.

## Instructions hidden in passages

A passage may contain text written to steer the judge ("ignore the previous
instructions..."). The prompt places the question, the answer and every
passage between markers that the text itself can never contain: any `<<<` or
`>>>` inside the data is broken up before the prompt is built, so a passage
cannot end its own block or open a fake one. The instructions say that
nothing between the markers is an instruction. And whatever the judge does,
its agreement resolves nothing. Tests in the repository check all three.

## What the record keeps

The judge appears in the record as a verifier, `llm_judge.<adapter>`, with
determinism `non_deterministic`. Its declaration carries the template id and
hash, the hash of the exact prompt, the model the provider says answered, and
the hash of the raw reply. The reply itself is not stored; each sentence's
evidence keeps the label, the passages cited and the judge's one-sentence
reason. The record is enough to show what was asked, of which model, and
what came back, without keeping a copy of every reply.
