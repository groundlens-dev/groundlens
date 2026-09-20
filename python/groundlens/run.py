# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""``verify_run()``: verify a whole agent execution, not one answer.

    MCP trace (tool calls, results, model turns)
        → event log
        → execution policy (ALLOW / REVIEW / DENY per step)
        → signed, hash-chained run record

Where :func:`groundlens.verify` seals what a model *said*, this seals what an
agent *did*. Both leave a signed record anyone can check offline.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from groundlens import _engine
from groundlens.record import IntegrityError


@dataclass(frozen=True)
class RunRecord:
    """A sealed run record. ``raw`` is the exact JSON the engine produced."""

    raw: dict[str, Any]

    @classmethod
    def from_json(cls, text: str) -> RunRecord:
        return cls(json.loads(text))

    @property
    def run_id(self) -> str:
        return self.raw["content"]["run_id"]

    @property
    def gate(self) -> str:
        """The gate verdict over the run: ``ALLOW``, ``REVIEW`` or ``DENY``."""
        return self.raw["content"]["gate"]

    @property
    def breaches(self) -> tuple[dict[str, Any], ...]:
        """Actions executed against the policy. Empty when there were none."""
        return tuple(self.raw["content"].get("breaches", ()))

    @property
    def record_hash(self) -> str:
        return self.raw["record_hash"]

    @property
    def policy_hash(self) -> str | None:
        return self.raw["content"].get("policy_hash")

    def to_json(self) -> str:
        return json.dumps(self.raw, ensure_ascii=False)

    def append_to(self, log: str | Path) -> None:
        with Path(log).open("a", encoding="utf-8") as f:
            f.write(self.to_json() + "\n")

    @staticmethod
    def read_log(log: str | Path) -> list[RunRecord]:
        text = Path(log).read_text(encoding="utf-8")
        return [RunRecord(json.loads(line)) for line in text.splitlines() if line.strip()]

    @staticmethod
    def verify_chain(records: Iterable[RunRecord]) -> int:
        """Recompute every hash, link and signature. Raises on the first break."""
        jsonl = "\n".join(r.to_json() for r in records)
        try:
            return _engine.run_record_verify(jsonl)
        except RuntimeError as e:  # the engine raises RuntimeError on a broken chain
            raise IntegrityError(str(e)) from e


def verify_run(
    trace: str | Path | Sequence[Mapping],
    policy: Mapping | str | Path,
    *,
    run_id: str,
    system: str,
    system_version: str | None = None,
    started_at: str | None = None,
    signing_key: str | None = None,
    previous: RunRecord | str | None = None,
    log: str | Path | None = None,
) -> RunRecord:
    """Verify an MCP execution ``trace`` under an execution ``policy`` and seal a record.

    Args:
        trace: the MCP execution as JSON-RPC messages. A path to a ``.jsonl``
            file, the JSON Lines text itself, or a sequence of message dicts.
            Each message may carry a top-level ``ts``.
        policy: the execution policy. A dict, a path (YAML or JSON), or the
            policy text itself.
        run_id: an id for this run.
        system: the deployed system the run belongs to.
        started_at: when the run began (ISO). The current time if absent.
        signing_key: 32-byte hex Ed25519 seed. An ephemeral key is used if absent.
        previous: the previous run record (or its ``record_hash``) to chain to.
        log: an append-only JSON Lines file; the record is appended and the
            chain continues from its last record.

    Returns:
        A :class:`RunRecord`. ``record.gate`` is ``ALLOW`` / ``REVIEW`` /
        ``DENY``; ``record.breaches`` lists any action executed against the policy.
    """
    previous_hash = previous.record_hash if isinstance(previous, RunRecord) else previous
    if log is not None and previous_hash is None:
        path = Path(log)
        if path.exists():
            existing = RunRecord.read_log(path)
            if existing:
                previous_hash = existing[-1].record_hash

    request = {
        "trace": _trace_text(trace),
        "policy_json": _policy_json(policy),
        "run_id": run_id,
        "system_id": system,
        "system_version": system_version,
        "started_at": started_at,
        "signing_key_hex": signing_key,
        "previous_record_hash": previous_hash,
    }
    record = RunRecord.from_json(_engine.run_verify_json(json.dumps(request)))
    if log is not None:
        record.append_to(log)
    return record


def _trace_text(trace: str | Path | Sequence[Mapping]) -> str:
    if isinstance(trace, Mapping):
        return json.dumps(trace, ensure_ascii=False)
    if isinstance(trace, (list, tuple)):
        return "\n".join(json.dumps(m, ensure_ascii=False) for m in trace)
    path = Path(trace)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return str(trace)


def _policy_json(policy: Mapping | str | Path) -> str:
    if isinstance(policy, Mapping):
        return json.dumps(policy, ensure_ascii=False)
    path = Path(policy)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            return _engine.yaml_to_json(text)
        return text
    text = str(policy)
    if text.lstrip().startswith("{"):
        return text
    return _engine.yaml_to_json(text)
