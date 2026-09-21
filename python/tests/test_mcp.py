# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The MCP server tools. The tool logic is tested directly; the server
registration is tested when the MCP SDK is installed (the ``[mcp]`` extra)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundlens import verify
from groundlens.mcp import tools

DENY_SHELL_POLICY = """
id: test_exec_v1
rules:
  - id: no-shell
    match: tool
    name: shell.exec
    effect: DENY
default: ALLOW
"""

TRACE = "\n".join(
    json.dumps(m)
    for m in [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "shell.exec", "arguments": {"cmd": "rm -rf /"}}},
        {"jsonrpc": "2.0", "id": 1, "result": {"isError": True, "content": [{"type": "text", "text": "blocked"}]}},
    ]
)


def test_verify_answer_flags_a_numeric_contradiction():
    out = tools.verify_answer(
        "The invoice total is 1,000 dollars.",
        [("invoice.pdf#p1", "The total amount due is 10,000 dollars.")],
        question="What is the invoice total?",
        locale="en",
    )
    assert out["decision"] == "FAIL"
    assert out["content_hash"].startswith("sha256:")
    assert any(e["verifier_id"] == "groundlens.numeric" and e["result"] == "contradicted" for e in out["evidence"])


def test_verify_answer_accepts_dicts_and_bare_strings():
    out = tools.verify_answer(
        "The total is 10,000 dollars.",
        [{"id": "s1", "text": "The total amount due is 10,000 dollars."}],
        locale="en",
    )
    assert out["decision"] in ("PASS", "REVIEW", "FAIL")
    out2 = tools.verify_answer("The total is 10,000 dollars.", ["The total is 10,000 dollars."], locale="en")
    assert out2["evidence"][0]["source_id"] == "source_1"


def test_verify_execution_denies_a_forbidden_tool():
    out = tools.verify_execution(TRACE, DENY_SHELL_POLICY, run_id="run_test", system="test-agent")
    assert out["gate"] == "DENY"
    assert out["run_id"] == "run_test"
    assert out["record_hash"].startswith("sha256:")


def test_verify_records_round_trip(tmp_path: Path):
    log = tmp_path / "records.jsonl"
    verify("The total is 10,000 dollars.", [("s", "The total amount due is 10,000 dollars.")],
           locale="en", log=log)
    verify("The invoice total is 1,000 dollars.", [("s", "The total amount due is 10,000 dollars.")],
           locale="en", log=log)
    out = tools.verify_records(log.read_text(encoding="utf-8"))
    assert out == {"ok": True, "verified": 2, "kind": "answer"}


def test_verify_records_detects_tampering(tmp_path: Path):
    log = tmp_path / "records.jsonl"
    verify("The invoice total is 1,000 dollars.", [("s", "The total amount due is 10,000 dollars.")],
           locale="en", log=log)
    lines = log.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["content"]["outcome"]["decision"] = "PASS"
    with pytest.raises(Exception):
        tools.verify_records(json.dumps(tampered))


def test_verify_records_empty_is_ok():
    assert tools.verify_records("") == {"ok": True, "verified": 0, "kind": "answer"}


def test_server_registers_the_three_tools():
    mcp = pytest.importorskip("mcp")  # noqa: F841 - only run with the [mcp] extra
    import asyncio

    from groundlens.mcp.server import build_server

    server = build_server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"verify_answer", "verify_run", "verify_records"} <= names
