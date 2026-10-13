# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Connectors to the tools developers already watch their applications with.

- :func:`otel`: OpenTelemetry spans and metrics, for Grafana, Jaeger, Datadog
  and any other OpenTelemetry backend. ``pip install "groundlens[otel]"``.
- :func:`langfuse`: the check inside the Langfuse trace, and the decision as
  a score. ``pip install "groundlens[langfuse]"``.
- :func:`grafana_dashboard`: the path of a Grafana dashboard for the metrics
  and spans :func:`otel` writes.

Each is an observer for :class:`groundlens.Verifier`. Imported on first use,
so the core keeps zero runtime dependencies.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any


# The connectors live in private modules (``_otel``, ``_langfuse``) so that
# importing them does not replace these functions with modules of that name.


def otel(tracer: Any = None, meter: Any = None, *, capture_text: bool = False, decorate: Any = None) -> Any:
    """An observer that writes each check as OpenTelemetry spans and metrics,
    through the providers your application configured. ``capture_text=True``
    adds the judge's prompt and reply to its span."""
    from groundlens.integrations._otel import otel as make

    return make(tracer, meter, capture_text=capture_text, decorate=decorate)


def langfuse(client: Any, *, capture_text: bool = False, score_name: str = "groundlens.decision") -> Any:
    """An observer that adds each check to the Langfuse trace it ran in, and
    its decision as the categorical score ``groundlens.decision``. ``client``
    is a Langfuse client (Python SDK v3 or v4), such as ``langfuse.get_client()``."""
    from groundlens.integrations._langfuse import langfuse as make

    return make(client, capture_text=capture_text, score_name=score_name)


def grafana_dashboard() -> Path:
    """The dashboard JSON to import into Grafana (Dashboards → New → Import)."""
    return Path(str(files("groundlens.integrations").joinpath("grafana-dashboard.json")))
