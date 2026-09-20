# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""verify_run(): MCP trace → event log → execution policy → signed run record."""

from __future__ import annotations

import pytest

from groundlens import RunRecord, verify_run
from groundlens.record import IntegrityError

POLICY = {
    "id": "eu_high_risk_v1",
    "rules": [{"id": "no-shell", "match": "tool", "name": "shell.exec", "effect": "DENY"}],
    "default": "ALLOW",
}

CLEAN = [
    {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
     "params": {"name": "crm.lookup", "arguments": {"account": 42}}, "ts": "2026-09-20T10:00:00Z"},
    {"jsonrpc": "2.0", "id": 1, "result": {"isError": False, "content": []}, "ts": "2026-09-20T10:00:01Z"},
]

SHELL = CLEAN + [
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "shell.exec", "arguments": {"cmd": "rm -rf /"}}, "ts": "2026-09-20T10:00:02Z"},
    {"jsonrpc": "2.0", "id": 2, "result": {"isError": True, "content": []}, "ts": "2026-09-20T10:00:03Z"},
]


def test_a_clean_run_is_allowed_and_verifies():
    r = verify_run(CLEAN, POLICY, run_id="run_1", system="agent", started_at="2026-09-20T10:00:00Z")
    assert r.gate == "ALLOW"
    assert r.policy_hash is not None
    RunRecord.verify_chain([r])


def test_a_forbidden_tool_is_denied():
    r = verify_run(SHELL, POLICY, run_id="run_1", system="agent", started_at="2026-09-20T10:00:00Z")
    assert r.gate == "DENY"
    RunRecord.verify_chain([r])


def test_log_chains_and_a_tampered_record_is_caught(tmp_path):
    log = tmp_path / "runs.jsonl"
    r1 = verify_run(CLEAN, POLICY, run_id="run_1", system="agent",
                    started_at="2026-09-20T10:00:00Z", log=log)
    r2 = verify_run(CLEAN, POLICY, run_id="run_2", system="agent",
                    started_at="2026-09-20T10:05:00Z", log=log)
    records = RunRecord.read_log(log)
    assert [x.run_id for x in records] == ["run_1", "run_2"]
    assert RunRecord.verify_chain(records) == 2

    records[0].raw["content"]["gate"] = "ALLOW" if r1.gate != "ALLOW" else "DENY"
    with pytest.raises(IntegrityError):
        RunRecord.verify_chain(records)
    assert r2.record_hash  # second record chained onto the first
