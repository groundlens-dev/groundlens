# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Observers and the connectors built on them: OpenTelemetry, Langfuse, Grafana.

Spans and metrics go to the OpenTelemetry SDK's in-memory exporters; the
Langfuse client is a stand-in with the two things the connector uses.
"""

from __future__ import annotations

import json
import logging
import re
from types import SimpleNamespace

import pytest

import groundlens as gl

sdk_trace = pytest.importorskip("opentelemetry.sdk.trace")
from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

PASSAGES = [("10k#p114", "UPS revenue was $91.0 billion in 2023.", {"entity": "UPS"})]
JUDGED = """id: judged
version: 1.0.0
extends: eu_ai_act_high_risk_v1
verifiers:
  forbidden: []
judge:
  required: true
"""


class Recorder:
    def __init__(self):
        self.events = []

    def on_check(self, event):
        self.events.append(event)


class Broken:
    def on_check(self, event):
        raise RuntimeError("the dashboard is down")


class ScriptedJudge:
    adapter = "scripted"
    model = "judge-test-1"

    def __init__(self, label):
        self.label = label

    def complete(self, system, user):
        ids = re.findall(r"^(c\d+): <<<", user, flags=re.M)
        return json.dumps({"claims": [{"id": i, "label": self.label, "passages": ["10k#p114"], "reason": "x"} for i in ids]}), None


def otel_setup():
    spans = InMemorySpanExporter()
    provider = sdk_trace.TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    return provider, spans, meters, reader


def metric_points(reader):
    out = {}
    for rm in reader.get_metrics_data().resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                out[m.name] = list(m.data.data_points)
    return out


def test_observers_hear_about_stored_records_only_and_cannot_break_a_check(tmp_path, caplog):
    seen = Recorder()
    v = gl.Verifier(sink=gl.sinks.jsonl(tmp_path), observers=[Broken(), seen])
    with caplog.at_level(logging.ERROR, logger="groundlens.observe"):
        record = v.check(answer="UPS revenue was $91.0 billion in 2023.", passages=PASSAGES)
    assert record.decision == "PASS"
    assert "the dashboard is down" in caplog.text
    (event,) = seen.events
    assert event.record.record_hash == record.record_hash
    assert [s.name for s in event.verifiers][:1] == ["groundlens.numeric"]
    assert event.start_ns <= event.engine.start_ns <= event.engine.end_ns <= event.store.start_ns <= event.end_ns
    assert event.judge is None and event.sign is None
    v.seal(answer="UPS revenue was $91.0 billion in 2023.", passages=PASSAGES)
    assert len(seen.events) == 1


def test_otel_writes_a_check_span_with_children_inside_the_callers_trace(tmp_path):
    provider, spans, meters, reader = otel_setup()
    tracer = provider.get_tracer("app")
    observer = gl.integrations.otel(provider.get_tracer("groundlens"), meters.get_meter("groundlens"))
    v = gl.Verifier(JUDGED, sink=gl.sinks.jsonl(tmp_path), judge=ScriptedJudge("unsupported"), observers=[observer])
    with tracer.start_as_current_span("answer") as parent:
        record = v.check(answer="UPS revenue was $91.0 billion in 2023.", passages=PASSAGES, scope={"entity": "UPS"})
    assert record.decision == "REVIEW"
    by_name = {s.name: s for s in spans.get_finished_spans()}
    check = by_name["groundlens.check"]
    assert check.parent.span_id == parent.get_span_context().span_id
    assert check.attributes["groundlens.decision"] == "REVIEW"
    assert check.attributes["groundlens.record.hash"] == record.record_hash
    assert check.attributes["groundlens.reason.details"].split("\n") == record.reasons
    assert check.attributes["groundlens.reasons"].split(", ") == gl.observe.reason_codes(record)
    judge = by_name["groundlens.judge"]
    assert judge.parent.span_id == check.context.span_id
    assert judge.attributes["gen_ai.request.model"] == "judge-test-1"
    assert "groundlens.judge.user" not in judge.attributes  # no text unless asked
    numeric = by_name["groundlens.numeric"]
    assert numeric.parent.span_id == by_name["groundlens.engine"].context.span_id
    assert check.start_time <= judge.start_time and by_name["groundlens.store"].end_time <= check.end_time
    points = metric_points(reader)
    assert {p.attributes["decision"]: p.value for p in points["groundlens.decisions"]} == {"REVIEW": 1}
    assert {p.attributes["stage"] for p in points["groundlens.check.duration"]} == {"total", "engine", "judge", "store"}
    assert {p.attributes["reason"] for p in points["groundlens.reasons"]} == set(gl.observe.reason_codes(record))


def test_otel_sends_the_judge_text_only_when_asked(tmp_path):
    provider, spans, meters, _ = otel_setup()
    observer = gl.integrations.otel(provider.get_tracer("g"), meters.get_meter("g"), capture_text=True)
    v = gl.Verifier(JUDGED, sink=gl.sinks.jsonl(tmp_path), judge=ScriptedJudge("supported"), observers=[observer])
    v.check(answer="UPS revenue was $91.0 billion in 2023.", passages=PASSAGES, scope={"entity": "UPS"})
    judge = next(s for s in spans.get_finished_spans() if s.name == "groundlens.judge")
    assert "UPS revenue" in judge.attributes["groundlens.judge.user"]


class LangfuseStandIn:
    """The two things the connector uses from a Langfuse client."""

    def __init__(self, tracer):
        self._otel_tracer = tracer
        self.scores = []

    def create_score(self, **kw):
        self.scores.append(kw)


def test_langfuse_puts_the_check_in_the_trace_and_the_decision_in_a_score(tmp_path):
    provider, spans, _, _ = otel_setup()
    client = LangfuseStandIn(provider.get_tracer("langfuse-sdk"))
    v = gl.Verifier(
        JUDGED, sink=gl.sinks.jsonl(tmp_path), judge=ScriptedJudge("unsupported"), observers=[gl.integrations.langfuse(client)]
    )
    with provider.get_tracer("app").start_as_current_span("answer") as parent:
        record = v.check(answer="UPS revenue was $91.0 billion in 2023.", passages=PASSAGES, scope={"entity": "UPS"})
    by_name = {s.name: s for s in spans.get_finished_spans()}
    check = by_name["groundlens.check"]
    assert check.attributes["langfuse.observation.type"] == "guardrail"
    assert check.attributes["langfuse.observation.level"] == "WARNING"
    assert by_name["groundlens.judge"].attributes["langfuse.observation.type"] == "generation"
    assert by_name["groundlens.judge"].attributes["langfuse.observation.model.name"] == "judge-test-1"
    (score,) = client.scores
    assert score["name"] == "groundlens.decision" and score["value"] == "REVIEW"
    assert score["data_type"] == "CATEGORICAL"
    assert score["trace_id"] == format(parent.get_span_context().trace_id, "032x")
    assert score["metadata"]["record_hash"] == record.record_hash


def test_the_langfuse_client_still_has_the_tracer_the_connector_uses():
    langfuse = pytest.importorskip("langfuse")
    client = langfuse.Langfuse(public_key="pk-lf-test", secret_key="sk-lf-test", tracing_enabled=False)
    assert hasattr(client, "_otel_tracer")
    assert callable(client.create_score)


def test_the_grafana_dashboard_queries_the_metrics_otel_writes():
    path = gl.integrations.grafana_dashboard()
    dash = json.loads(path.read_text())
    exprs = " ".join(t.get("expr", "") + t.get("query", "") for p in dash["panels"] for t in p["targets"])
    for name in ("groundlens_decisions_total", "groundlens_reasons_total", "groundlens_check_duration_seconds_bucket"):
        assert name in exprs
    assert 'name = "groundlens.check"' in exprs
    assert len({p["id"] for p in dash["panels"]}) == len(dash["panels"])


def test_the_core_imports_no_telemetry():
    import subprocess
    import sys

    code = "import sys, groundlens; v = groundlens.Verifier(); print('opentelemetry' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_spans_reach_the_global_provider_by_default(tmp_path):
    seen = SimpleNamespace(started=0)

    class Tracer:
        def start_span(self, *a, **kw):
            seen.started += 1
            return trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)

    observer = gl.integrations.otel(Tracer())
    gl.Verifier(sink=gl.sinks.jsonl(tmp_path), observers=[observer]).check(
        answer="UPS revenue was $91.0 billion in 2023.", passages=PASSAGES
    )
    assert seen.started >= 4


@pytest.mark.parametrize(
    "reason, code",
    [
        ("c5: groundlens.numeric contradicted: €4,980 thousand not in sources", "groundlens.numeric.contradicted"),
        ("c2: groundlens.scope contradicted: 2024 found only in lm-2024#p08", "groundlens.scope.contradicted"),
        ("c2: verifiers disagree on this claim", "conflict"),
        ("mandatory_review: risk class credit_limit_change always goes to review", "mandatory_review"),
        ("missing_scope: the request does not say its entity", "missing_scope"),
        ("c1: llm_judge.openai_compatible unsupported: cites p12: EBIT, not EBITDA", "llm_judge.openai_compatible.unsupported"),
        ("c1: llm_judge.bedrock could not label: timeout", "llm_judge.bedrock.could_not_label"),
        ("c3: no admitted verifier produced evidence for this claim", "unresolved"),
        ("c3: nli.deberta score 0.700000 below 0.85", "nli.deberta.below_threshold"),
    ],
)
def test_reasons_become_codes_a_dashboard_can_group_by(reason, code):
    assert gl.observe.reason_code(reason) == code
