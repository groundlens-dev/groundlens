# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""A credit assistant that checks every answer, watched in Grafana or Langfuse.

    pip install "groundlens[otel,langfuse]" opentelemetry-sdk opentelemetry-exporter-otlp-proto-http

    # Grafana: docker run -p 3000:3000 -p 4318:4318 grafana/otel-lgtm
    python credit_copilot.py grafana --minutes 10

    # Langfuse: a Langfuse project, and its keys in LANGFUSE_PUBLIC_KEY,
    # LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL
    python credit_copilot.py langfuse --case ebitda --case other-borrower

The assistant is simulated: it answers from ``cases.json``, and its retrieval
and generation steps are stand-ins that wait a fixed time. Everything GroundLens
does is real: the checks, the decisions, the signed records in ``records/``,
and every span and metric it sends.

``--judge-model`` adds a judge, any OpenAI-compatible endpoint
(``--judge-base-url``, key in ``JUDGE_API_KEY``), and switches to the
``credit_desk_judged`` policy. It is the only way the ``wrong-line`` case,
whose figure is real but from the wrong line, is caught.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

import groundlens as gl

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))


def passages(case: dict) -> list[tuple[str, str, dict]]:
    return [(pid, DATA["passages"][pid]["text"], {"entity": DATA["passages"][pid]["entity"]}) for pid in case["retrieved"]]


def demo_key() -> str:
    """A development key kept next to the records, so every run signs with the
    same key. A real deployment signs with a KMS or HSM key (groundlens.signers)."""
    path = HERE / "records" / "demo.key"
    if not path.exists():
        path.write_text(gl.signers.local_key().seed_hex, encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def make_verifier(args, observers) -> gl.Verifier:
    judge = None
    policy = HERE / "credit_desk.yaml"
    if args.judge_model:
        import openai

        client = openai.OpenAI(base_url=args.judge_base_url, api_key=os.environ.get("JUDGE_API_KEY", "none"))
        judge = gl.judges.openai_compatible(client, args.judge_model)
        policy = HERE / "credit_desk_judged.yaml"
    return gl.Verifier(
        policy,
        signer=gl.signers.local_key(demo_key()),
        sink=gl.sinks.jsonl(HERE / "records", chain=args.target),
        judge=judge,
        observers=observers,
    )


def pick(args) -> list[dict]:
    cases = {c["id"]: c for c in DATA["cases"]}
    if args.case:
        return [cases[c] for c in args.case]
    pool = [c for c in DATA["cases"] if not c.get("judge_only") or args.judge_model]
    return random.choices(pool, weights=[c["weight"] or 4 for c in pool])


def run_grafana(args) -> None:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": "credit-copilot"})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(f"{args.otlp}/v1/traces")))
    trace.set_tracer_provider(tracer_provider)
    reader = PeriodicExportingMetricReader(OTLPMetricExporter(f"{args.otlp}/v1/metrics"), export_interval_millis=5000)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    verifier = make_verifier(args, [gl.integrations.otel()])
    tracer = trace.get_tracer("credit-copilot")
    for case in loop(args):
        with tracer.start_as_current_span("credit-copilot.answer") as root:
            root.set_attribute("app.case", case["id"])
            with tracer.start_as_current_span("retrieve passages"):
                time.sleep(0.12)
            with tracer.start_as_current_span("generate answer"):
                time.sleep(0.9)
            record = verifier.check(
                question=case["question"],
                answer=case["answer"],
                passages=passages(case),
                scope=case["scope"] or None,
                risk_class=case.get("risk_class"),
            )
        print(f"{case['id']:<16} {record.decision}")
    tracer_provider.shutdown()
    metrics.get_meter_provider().shutdown()


def run_langfuse(args) -> None:
    from langfuse import Langfuse

    # Name the service, as an application would; Langfuse shows it on each trace.
    os.environ.setdefault("OTEL_SERVICE_NAME", "credit-copilot")
    client = Langfuse()
    verifier = make_verifier(args, [gl.integrations.langfuse(client)])
    for case in loop(args):
        with client.start_as_current_observation(name="credit-copilot.answer", input=case["question"]) as root:
            with client.start_as_current_observation(
                name="retrieve passages", as_type="retriever", input=case["question"]
            ) as step:
                time.sleep(0.12)
                step.update(output=case["retrieved"])
            with client.start_as_current_observation(name="generate answer", input=case["question"]) as step:
                time.sleep(0.9)
                step.update(output=case["answer"])
            record = verifier.check(
                question=case["question"],
                answer=case["answer"],
                passages=passages(case),
                scope=case["scope"] or None,
                risk_class=case.get("risk_class"),
            )
            # What the analyst sees depends on the decision: a FAIL is never shown.
            shown = {"PASS": case["answer"], "REVIEW": "Held for review", "FAIL": "Not shown"}[record.decision]
            root.update(output=shown)
        print(f"{case['id']:<16} {record.decision}")
    client.flush()


def loop(args):
    end = time.time() + args.minutes * 60
    while True:
        yield from pick(args)
        if args.case or time.time() >= end:
            return
        time.sleep(random.uniform(0.2, 1.5))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", choices=["grafana", "langfuse"])
    parser.add_argument("--case", action="append", help="run these cases once, in order (ids from cases.json)")
    parser.add_argument("--minutes", type=float, default=0, help="keep answering random cases this long")
    parser.add_argument("--otlp", default="http://localhost:4318", help="OpenTelemetry collector, OTLP over HTTP")
    parser.add_argument("--judge-model", help="model for the judge, on an OpenAI-compatible endpoint")
    parser.add_argument("--judge-base-url", default="https://api.openai.com/v1")
    args = parser.parse_args()
    (HERE / "records").mkdir(exist_ok=True)
    {"grafana": run_grafana, "langfuse": run_langfuse}[args.target](args)


if __name__ == "__main__":
    main()
