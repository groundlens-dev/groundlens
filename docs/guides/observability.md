# Watch checks in Grafana or Langfuse

The record is the evidence; it lives in your sink. The people who run the
application also want to see the checks where they already look: next to the
model calls in Langfuse, or on a Grafana dashboard with the rest of the
service. GroundLens sends each check there through **observers**.

An observer is told about a check after its record is stored. It reports; it
never changes a decision. If one fails, the error is logged and the check
returns its record as if nothing happened.

## Langfuse

```{code-block} python
from langfuse import get_client
import groundlens as gl

langfuse = get_client()   # LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL

verifier = gl.Verifier(
    "eu_ai_act_high_risk_v1",
    sink=gl.sinks.jsonl("records/"),
    observers=[gl.integrations.langfuse(langfuse)],
)

with langfuse.start_as_current_observation(name="answer", input=question):
    answer = ...                          # your retrieval and your model call
    record = verifier.check(question=question, answer=answer, passages=passages, scope=scope)
```

`pip install "groundlens[langfuse]"`. Works with Langfuse Cloud and
self-hosted Langfuse, Python SDK v3 or v4.

Call `check` inside the observation that produced the answer, and the trace
of that answer gets:

| In Langfuse | What it is |
|---|---|
| `groundlens.check` | A guardrail observation. Level `WARNING` when the answer goes to review, `ERROR` when it fails. Its output is the decision; its status message lists the reasons, one per line. |
| `groundlens.judge` | A generation with the judge's model, when the policy uses a judge. Next to your own model calls, with its latency. |
| `groundlens.engine` and one span per verifier | How long each check took. Exact checks take about a millisecond. |
| `groundlens.store` | Writing the record to your sink. |
| Score `groundlens.decision` | Categorical, on the trace: `PASS`, `REVIEW` or `FAIL`, with the reason codes as its comment. Filter traces by it, chart it, export it. |

## Grafana, and any OpenTelemetry backend

```{code-block} python
verifier = gl.Verifier(
    "eu_ai_act_high_risk_v1",
    sink=gl.sinks.jsonl("records/"),
    observers=[gl.integrations.otel()],
)
```

`pip install "groundlens[otel]"`. The observer uses the tracer and meter
providers your application configured, so the spans land in the trace of the
request that produced the answer, and go wherever your other spans go:
Grafana Tempo, Jaeger, Datadog, Honeycomb, an OpenTelemetry collector. If your
application configures no providers, nothing is sent.

Spans:

```text
groundlens.check            groundlens.decision, groundlens.reasons, policy, record id and hash
├── groundlens.judge        gen_ai.* attributes, when the policy uses a judge
├── groundlens.engine
│   ├── groundlens.numeric  one span per verifier, named by its id
│   └── ...
├── groundlens.sign         when an external signer signs
└── groundlens.store
```

Metrics:

| Metric | Type | Attributes |
|---|---|---|
| `groundlens.decisions` | counter | `decision`, `policy` |
| `groundlens.reasons` | counter | `reason`, `decision` |
| `groundlens.check.duration` | histogram, seconds | `stage` (`total`, `judge`, `engine`, `sign`, `store`), `policy` |

In Prometheus these are `groundlens_decisions_total`,
`groundlens_reasons_total` and `groundlens_check_duration_seconds`.

`reason` is a code, not the reason itself: `groundlens.numeric.contradicted`,
`groundlens.scope.contradicted`, `llm_judge.bedrock.unsupported`,
`mandatory_review`, `missing_scope`, `conflict`. The full reasons name claims
and figures, so they differ on almost every record; they are on the span as
`groundlens.reason.details`. `groundlens.observe.reason_code` turns one into
the other.

### The dashboard

The connector ships a Grafana dashboard: decisions, reasons, latency by stage,
and the latest `REVIEW` and `FAIL` with a link to each trace in Tempo.

```{code-block} python
print(gl.integrations.grafana_dashboard())   # the path of the JSON file
```

In Grafana: **Dashboards → New → Import**, upload the file, and pick your
Prometheus and Tempo data sources.

## What is sent

No text of the question, the answer or the passages leaves the process. Spans
carry the decision, reason codes and details, the policy, and the record's id
and hash. The reason details quote the figures that did not match, such as
`€4,980 thousand`; if those are sensitive in your deployment, drop
`groundlens.reason.details` in your collector.

`capture_text=True`, on either connector, adds the judge's prompt and reply to
its span: useful when you debug the judge, and the same text your model
provider already receives.

## Try it

`examples/observability/` runs a small credit assistant against a local
Grafana (`docker run -p 3000:3000 -p 4318:4318 grafana/otel-lgtm`) or a
Langfuse project. Its retrieval and generation are stand-ins; the checks,
records, spans and metrics are real.

## Your own observer

Anything with `on_check(event)` is an observer. The event is a
`groundlens.observe.CheckEvent`: the stored record, and the start and end of
each step in nanoseconds since the epoch.

```{code-block} python
class Alert:
    def on_check(self, event):
        if event.record.decision == "FAIL":
            pager.send(event.record.record_id, event.record.reasons)
```

The durations are not in the record. A record's content is the same on every
machine; how long it took to produce is not.
