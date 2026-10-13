# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""OpenTelemetry: every check as a span in your traces, and as metrics.

    verifier = groundlens.Verifier(..., observers=[groundlens.integrations.otel()])

Uses the tracer and meter providers your application already configured, so
the spans land in the same trace as the request that produced the answer, and
go wherever your other spans go: Grafana Tempo, Jaeger, Datadog, Honeycomb, an
OpenTelemetry collector. Install with ``pip install "groundlens[otel]"``.

Spans::

    groundlens.check                  decision, reasons, policy, record
    ├── groundlens.judge              gen_ai.* attributes, when there is a judge
    ├── groundlens.engine
    │   ├── groundlens.numeric        one span per verifier, named by its id
    │   └── groundlens.scope ...
    ├── groundlens.sign               when an external signer signs
    └── groundlens.store

Metrics:

- ``groundlens.decisions``: counter, by ``decision`` and ``policy``.
- ``groundlens.reasons``: counter, by ``reason`` (a code such as
  ``groundlens.numeric.contradicted``, see :func:`groundlens.observe.reason_code`)
  and ``decision``.
- ``groundlens.check.duration``: histogram in seconds, by ``stage``
  (``total``, ``judge``, ``engine``, ``sign``, ``store``).

No text of the question, the answer or the passages is sent unless you pass
``capture_text=True``; then the judge span carries the prompt and the reply.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from groundlens.observe import CheckEvent, Span, reason_codes

try:
    from opentelemetry import metrics, trace
    from opentelemetry.trace import SpanKind, Status, StatusCode
except ImportError as e:  # pragma: no cover - exercised only without the extra
    raise ImportError('the OpenTelemetry connector needs: pip install "groundlens[otel]"') from e

SCOPE = "groundlens"

#: Histogram boundaries in seconds, from half a millisecond to a minute.
BUCKETS = [0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]

#: Extra attributes for one span: ``(kind, event, step) -> attributes``. Kind is
#: ``check``, ``judge``, ``engine``, ``verifier``, ``sign`` or ``store``.
Decorate = Callable[[str, CheckEvent, Span | None], dict[str, Any]]


def _version() -> str:
    from groundlens import __version__

    return __version__


class OpenTelemetry:
    """An observer that writes spans and metrics. See the module docs."""

    def __init__(
        self,
        tracer: Any = None,
        meter: Any = None,
        *,
        capture_text: bool = False,
        decorate: Decorate | None = None,
    ) -> None:
        self.tracer = tracer or trace.get_tracer(SCOPE, _version())
        meter = meter or metrics.get_meter(SCOPE, _version())
        self.capture_text = capture_text
        self.decorate = decorate
        self.decisions = meter.create_counter(
            "groundlens.decisions", unit="{answer}", description="Answers checked, by decision"
        )
        self.reasons = meter.create_counter(
            "groundlens.reasons", unit="{reason}", description="Why answers did not pass"
        )
        self.duration = meter.create_histogram(
            "groundlens.check.duration",
            unit="s",
            description="Time spent checking an answer, by stage",
            # Exact checks take about a millisecond and a judge seconds; the SDK's
            # default boundaries (0, 5, 10... meant for milliseconds) fit neither.
            explicit_bucket_boundaries_advisory=BUCKETS,
        )
        #: The ``groundlens.check`` span of the last event, for connectors that
        #: attach something to it afterwards.
        self.last_span: Any = None

    def on_check(self, event: CheckEvent) -> None:
        self._trace(event)
        self._measure(event)

    def _attrs(self, kind: str, event: CheckEvent, step: Span | None, base: dict[str, Any]) -> dict[str, Any]:
        if self.decorate is not None:
            base.update(self.decorate(kind, event, step))
        return {k: v for k, v in base.items() if v is not None}

    def _trace(self, event: CheckEvent) -> None:
        r = event.record
        check = self.tracer.start_span(
            "groundlens.check",
            kind=SpanKind.INTERNAL,
            start_time=event.start_ns,
            attributes=self._attrs(
                "check",
                event,
                None,
                {
                    "groundlens.decision": r.decision,
                    # Strings, not arrays: every tracing backend can show and
                    # filter a string; not all of them do arrays.
                    "groundlens.reasons": ", ".join(reason_codes(r)) or None,
                    "groundlens.reason.details": "\n".join(r.reasons) or None,
                    "groundlens.policy.id": r.policy_id,
                    "groundlens.policy.hash": r.policy_hash,
                    "groundlens.risk_class": r.risk_class,
                    "groundlens.record.id": r.record_id,
                    "groundlens.record.hash": r.record_hash,
                    "groundlens.engine.version": r.engine_version,
                    "groundlens.retries": event.retries,
                },
            ),
        )
        ctx = trace.set_span_in_context(check)
        if event.judge is not None:
            j = event.judge
            attrs = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": j.adapter,
                "gen_ai.request.model": j.model,
                "error.type": j.error.split(":", 1)[0] if j.error else None,
            }
            if self.capture_text:
                attrs["groundlens.judge.system"] = j.system
                attrs["groundlens.judge.user"] = j.user
                attrs["groundlens.judge.response"] = j.response
            span = self.tracer.start_span(
                "groundlens.judge",
                context=ctx,
                kind=SpanKind.CLIENT,
                start_time=j.start_ns,
                attributes=self._attrs("judge", event, j, attrs),
            )
            if j.error:
                span.set_status(Status(StatusCode.ERROR, j.error))
            span.end(end_time=j.end_ns)
        engine = self.tracer.start_span(
            "groundlens.engine",
            context=ctx,
            start_time=event.engine.start_ns,
            attributes=self._attrs("engine", event, event.engine, {}),
        )
        engine_ctx = trace.set_span_in_context(engine)
        for v in event.verifiers:
            span = self.tracer.start_span(
                v.name,
                context=engine_ctx,
                start_time=v.start_ns,
                attributes=self._attrs("verifier", event, v, {"groundlens.verifier.id": v.name}),
            )
            span.end(end_time=v.end_ns)
        engine.end(end_time=event.engine.end_ns)
        for kind, step in (("sign", event.sign), ("store", event.store)):
            if step is None:
                continue
            span = self.tracer.start_span(
                f"groundlens.{kind}", context=ctx, start_time=step.start_ns, attributes=self._attrs(kind, event, step, {})
            )
            span.end(end_time=step.end_ns)
        check.end(end_time=event.end_ns)
        self.last_span = check

    def _measure(self, event: CheckEvent) -> None:
        r = event.record
        self.decisions.add(1, {"decision": r.decision, "policy": r.policy_id})
        for code in reason_codes(r):
            self.reasons.add(1, {"reason": code, "decision": r.decision})
        stages = {"total": event.duration_ms, "engine": event.engine.duration_ms}
        for name, step in (("judge", event.judge), ("sign", event.sign), ("store", event.store)):
            if step is not None:
                stages[name] = step.duration_ms
        for stage, ms in stages.items():
            self.duration.record(ms / 1000, {"stage": stage, "policy": r.policy_id})


def otel(
    tracer: Any = None, meter: Any = None, *, capture_text: bool = False, decorate: Decorate | None = None
) -> OpenTelemetry:
    """An observer for :class:`groundlens.Verifier` that writes OpenTelemetry
    spans and metrics through the providers your application configured."""
    return OpenTelemetry(tracer, meter, capture_text=capture_text, decorate=decorate)
