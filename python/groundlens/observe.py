# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Hand each check to the tools you already watch your application with.

    verifier = groundlens.Verifier(
        policy="eu_ai_act_high_risk_v1",
        sink=groundlens.sinks.jsonl("records/"),
        observers=[groundlens.integrations.otel()],
    )

After a record is stored, :class:`~groundlens.Verifier` calls every observer
with a :class:`CheckEvent`: the record, and how long each part took. An
observer reports; it never decides. If one raises, the error is logged and the
check returns its record as if nothing happened.

The durations are not in the record. A record's content is the same on every
machine; how long it took to produce is not.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

from groundlens.record import Record

log = logging.getLogger("groundlens.observe")


@dataclass(frozen=True)
class Span:
    """One timed step. Times are nanoseconds since the Unix epoch."""

    name: str
    start_ns: int
    end_ns: int

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1e6


@dataclass(frozen=True)
class JudgeCall(Span):
    """The judge call, when the policy asked for one."""

    adapter: str = ""
    model: str = ""
    error: str | None = None
    #: The reply as the model sent it. Observers send it only if asked to.
    response: str | None = None
    system: str = ""
    user: str = ""


@dataclass(frozen=True)
class CheckEvent:
    """One answer checked: the stored record and the time each step took."""

    record: Record
    start_ns: int
    end_ns: int
    #: Each verifier the engine ran, in order. Their times are measured inside
    #: the engine and laid end to end from ``engine.start_ns``.
    verifiers: tuple[Span, ...]
    #: The whole engine call: every verifier, the policy and the seal.
    engine: Span
    judge: JudgeCall | None = None
    #: The external signer, when there is one.
    sign: Span | None = None
    #: The sink's append, retries included.
    store: Span | None = None
    #: Chain conflicts retried before the record was stored.
    retries: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1e6


_CLAIM = re.compile(r"^c\d+: ")
_REQUEST = re.compile(r"^([a-z_]+): ")
_VERIFIER = [
    (re.compile(r"^(\S+) contradicted"), "contradicted"),
    (re.compile(r"^(\S+) unsupported"), "unsupported"),
    (re.compile(r"^(\S+) could not label"), "could_not_label"),
    (re.compile(r"^(\S+) could not check"), "could_not_check"),
    (re.compile(r"^(\S+) score \S+ inside guard band"), "guard_band"),
    (re.compile(r"^(\S+) score \S+ below"), "below_threshold"),
]


def reason_code(reason: str) -> str:
    """A short, stable code for one of a record's reasons, fit for a metric
    label or a filter: ``groundlens.numeric.contradicted``,
    ``mandatory_review``, ``conflict``. The reason itself names the claim and
    the figures, so it is different on almost every record."""
    text = _CLAIM.sub("", reason)
    if text == reason and (m := _REQUEST.match(reason)):
        return m.group(1)
    for pattern, what in _VERIFIER:
        if m := pattern.match(text):
            return f"{m.group(1)}.{what}"
    if text.startswith("verifiers disagree"):
        return "conflict"
    if text.startswith("no admitted verifier"):
        return "unresolved"
    return "other"


def reason_codes(record: Record) -> list[str]:
    """The distinct :func:`reason_code` of a record's reasons, in order."""
    return list(dict.fromkeys(reason_code(r) for r in record.reasons))


class Observer(Protocol):
    """Anything with ``on_check(event)``. Called after the record is stored."""

    def on_check(self, event: CheckEvent) -> None: ...


def notify(observers: tuple[Observer, ...], event: CheckEvent) -> None:
    """Call each observer; log what they raise and carry on."""
    for observer in observers:
        try:
            observer.on_check(event)
        except Exception:  # noqa: BLE001 - an observer must never change a check
            log.exception("observer %r failed; the record was stored", observer)
