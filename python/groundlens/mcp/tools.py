# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The verification tools, as plain functions.

These wrap the engine (:func:`groundlens.verify`, :func:`groundlens.verify_run`,
:class:`groundlens.Record`) and return JSON-serialisable dicts. They have no
dependency on the MCP SDK, so they can be tested directly; :mod:`groundlens.mcp.server`
registers them as MCP tools.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from groundlens import Record, RunRecord, verify, verify_run

RUN_SCHEMA = "groundlens.run-record/1"


def _sources(sources: Sequence[Any]) -> list[tuple[str, str]]:
    """Accept ``[[id, text], ...]``, ``[{"id":..., "text":...}, ...]`` or ``[text, ...]``."""
    out: list[tuple[str, str]] = []
    for i, s in enumerate(sources):
        if isinstance(s, Mapping):
            out.append((str(s.get("id", f"source_{i + 1}")), str(s["text"])))
        elif isinstance(s, (list, tuple)):
            sid, text = s
            out.append((str(sid), str(text)))
        else:
            out.append((f"source_{i + 1}", str(s)))
    return out


def verify_answer(
    answer: str,
    sources: Sequence[Any],
    question: str | None = None,
    locale: str = "und",
    policy: str | None = None,
) -> dict[str, Any]:
    """Verify an answer against its sources under a policy; return the sealed record.

    Args:
        answer: the model output to verify.
        sources: the retrieved sources, as ``(id, text)`` pairs, ``{"id","text"}``
            dicts, or bare strings.
        question: what the model was asked. Never a source.
        locale: how the documents write numbers (``"en"``, ``"es"``, ...). Default ``"und"``.
        policy: a built-in policy name (``"eu_ai_act_high_risk_v1"``), a path, or YAML.
            ``None`` uses ``groundlens_default_v1``.
    """
    record = verify(answer, _sources(sources), question=question, locale=locale, policy=policy)
    return {
        "decision": record.decision,
        "policy_id": record.policy_id,
        "policy_hash": record.policy_hash,
        "content_hash": record.content_hash,
        "record_hash": record.record_hash,
        "report": record.report(),
        "regulatory_mapping": list(record.regulatory_mapping),
        "evidence": [
            {
                "verifier_id": e.verifier_id,
                "claim_id": e.claim_id,
                "result": e.result,
                "score": e.score,
                "source_id": e.source_id,
                "source_text": e.source_text,
                "notes": list(e.notes),
            }
            for e in record.evidence
        ],
        "record": json.loads(record.to_json()),
    }


def verify_execution(
    trace: str,
    policy: str,
    run_id: str,
    system: str,
    system_version: str | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    """Verify an MCP execution trace under an execution policy; return the run record.

    Args:
        trace: the MCP execution as JSON-RPC messages (JSON Lines text).
        policy: the execution policy, as YAML/JSON text or a path.
        run_id: an id for this run.
        system: the deployed system the run belongs to.
        system_version: the version of that system, if known.
        started_at: when the run began (ISO). The current time if absent.
    """
    record = verify_run(
        trace,
        policy,
        run_id=run_id,
        system=system,
        system_version=system_version,
        started_at=started_at,
    )
    return {
        "gate": record.gate,
        "breaches": list(record.breaches),
        "run_id": record.run_id,
        "policy_hash": record.policy_hash,
        "record_hash": record.record_hash,
        "record": record.raw,
    }


def verify_records(records: str) -> dict[str, Any]:
    """Verify a log of records offline: every hash, every link, every signature.

    Args:
        records: the JSON Lines text of a records log. Answer records and run
            records are both accepted; the log's schema selects the check.

    Returns:
        ``{"ok": True, "verified": <count>, "kind": "answer"|"run"}`` when the
        chain is intact. Raises if any record or link was altered.
    """
    lines = [ln for ln in records.splitlines() if ln.strip()]
    if not lines:
        return {"ok": True, "verified": 0, "kind": "answer"}
    first = json.loads(lines[0])
    is_run = first.get("content", {}).get("schema") == RUN_SCHEMA
    if is_run:
        count = RunRecord.verify_chain([RunRecord.from_json(ln) for ln in lines])
        kind = "run"
    else:
        count = Record.verify_chain([Record.from_json(ln) for ln in lines])
        kind = "answer"
    return {"ok": True, "verified": count, "kind": kind}
