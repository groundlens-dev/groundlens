# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Langfuse: every check inside the trace of the answer it checked.

    from langfuse import get_client
    langfuse = get_client()
    verifier = groundlens.Verifier(..., observers=[groundlens.integrations.langfuse(langfuse)])

Call ``check`` inside the observation that produced the answer (an
``@observe`` function, or ``with langfuse.start_as_current_span(...)``) and
the check appears in that trace:

- ``groundlens.check``, a guardrail observation, at level ``WARNING`` when the
  answer goes to review and ``ERROR`` when it fails;
- the judge as a generation, with its model, so it sits next to your own
  model calls;
- each verifier, the signer and the store as spans, with their latency;
- the decision as the categorical score ``groundlens.decision`` on the trace,
  with the reasons as its comment, so you can filter traces and chart it.

Works with Langfuse Cloud and self-hosted Langfuse, Python SDK v3 or v4. Install with
``pip install "groundlens[langfuse]"``.
"""

from __future__ import annotations

import logging
from typing import Any

from groundlens.integrations._otel import OpenTelemetry
from groundlens.observe import CheckEvent, Span, reason_codes

log = logging.getLogger("groundlens.integrations.langfuse")

_TYPE = "langfuse.observation.type"
_LEVEL = "langfuse.observation.level"
_MODEL = "langfuse.observation.model.name"
_STATUS = "langfuse.observation.status_message"
_INPUT = "langfuse.observation.input"
_OUTPUT = "langfuse.observation.output"
_METADATA = "langfuse.observation.metadata"

LEVELS = {"PASS": "DEFAULT", "REVIEW": "WARNING", "FAIL": "ERROR"}


class Langfuse:
    """An observer that writes to a Langfuse client. See the module docs."""

    def __init__(self, client: Any, *, capture_text: bool = False, score_name: str = "groundlens.decision") -> None:
        self.client = client
        self.capture_text = capture_text
        self.score_name = score_name
        # The client's own tracer: its spans pass Langfuse's project filter and
        # go to the same project as the rest of the trace.
        tracer = getattr(client, "_otel_tracer", None)
        self.otel = OpenTelemetry(tracer, capture_text=capture_text, decorate=self._decorate)

    def _decorate(self, kind: str, event: CheckEvent, step: Span | None) -> dict[str, Any]:
        r = event.record
        if kind == "check":
            attrs = {
                _TYPE: "guardrail",
                _LEVEL: LEVELS.get(r.decision, "DEFAULT"),
                _OUTPUT: r.decision,
                _METADATA + ".record_id": r.record_id,
                _METADATA + ".policy": r.policy_id,
            }
            if r.reasons:
                attrs[_STATUS] = "\n".join(r.reasons)
            return attrs
        if kind == "judge" and event.judge is not None:
            j = event.judge
            attrs = {_TYPE: "generation", _MODEL: j.model}
            if j.error:
                attrs[_LEVEL] = "ERROR"
                attrs[_STATUS] = j.error
            if self.capture_text:
                attrs[_INPUT] = f"{j.system}\n\n{j.user}"
                attrs[_OUTPUT] = j.response
            return attrs
        return {_TYPE: "span"}

    def on_check(self, event: CheckEvent) -> None:
        self.otel.on_check(event)
        span = self.otel.last_span
        ctx = span.get_span_context()
        r = event.record
        self.client.create_score(
            name=self.score_name,
            value=r.decision,
            data_type="CATEGORICAL",
            trace_id=format(ctx.trace_id, "032x"),
            comment=", ".join(reason_codes(r)) or None,
            metadata={"record_id": r.record_id, "record_hash": r.record_hash, "policy": r.policy_id},
        )


def langfuse(client: Any, *, capture_text: bool = False, score_name: str = "groundlens.decision") -> Langfuse:
    """An observer for :class:`groundlens.Verifier` that adds each check, and
    its decision as a score, to the Langfuse trace it ran in."""
    return Langfuse(client, capture_text=capture_text, score_name=score_name)
