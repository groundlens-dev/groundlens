# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The GroundLens MCP server.

Exposes verification as tools an agent (or any MCP client) can call: verify an
answer, verify an execution trace, or verify a log of records offline. It is a
thin layer over the engine and runs over stdio.

The MCP SDK is an optional dependency, installed with ``pip install groundlens[mcp]``.
Importing this module without it raises a clear error.
"""

from __future__ import annotations

from typing import Any

from groundlens.mcp import tools

try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError as e:  # pragma: no cover - exercised only without the extra
    raise ModuleNotFoundError(
        "the GroundLens MCP server needs the MCP SDK. Install it with: pip install 'groundlens[mcp]'"
    ) from e


def build_server() -> "MCPServer":
    """Build the MCP server with the three verification tools registered."""
    from groundlens import __version__

    server = MCPServer(
        "groundlens",
        title="GroundLens",
        description=(
            "Guardrails for LLM answers. Checks an LLM answer against its sources without a "
            "model, decides PASS, REVIEW or FAIL under a policy, and keeps a signed record."
        ),
        version=__version__,
        website_url="https://groundlens.dev",
        instructions=(
            "GroundLens: guardrails for LLM answers. Before you send an answer written from "
            "documents, call verify_answer with the answer and the passages it came from. It "
            "checks every figure (amounts, rates, percentages, dates, units, and figures the "
            "answer computed) against the passages without a model, and returns PASS, REVIEW "
            "or FAIL with the reasons. On FAIL, fix the figures the reasons name; on REVIEW, "
            "say what could not be confirmed. Pass scope (e.g. {\"entity\": \"ACME\"}) to "
            "fail figures taken from another company. verify_records checks a log of records "
            "offline; verify_run gates an MCP execution trace under an execution policy."
        ),
    )

    @server.tool(name="verify_answer")
    def verify_answer(
        answer: str,
        sources: list[Any],
        question: str | None = None,
        locale: str = "und",
        policy: str | None = None,
        scope: dict[str, str] | None = None,
        risk_class: str | None = None,
    ) -> dict[str, Any]:
        """Check an answer against the passages it was written from, before you send it.

        Every figure must be in the passages or follow from figures that are; no model
        is used. Returns PASS, REVIEW or FAIL with the reasons, and the signed record.

        sources: (id, text) pairs, {"id","text","provenance"} dicts, or bare strings.
        policy: a built-in name (e.g. "eu_ai_act_high_risk_v1"), a path, or YAML.
        scope: what the request is about, e.g. {"entity": "UPS"}; a figure taken
        from a source whose provenance is another entity fails.
        risk_class: the request's risk class, when the policy defines them.
        Returns the decision (PASS/REVIEW/FAIL), the evidence, the regulatory
        mapping and the record with its content hash.
        """
        return tools.verify_answer(
            answer, sources, question=question, locale=locale, policy=policy, scope=scope, risk_class=risk_class
        )

    @server.tool(name="verify_run")
    def verify_run(
        trace: str,
        policy: str,
        run_id: str,
        system: str,
        system_version: str | None = None,
        started_at: str | None = None,
    ) -> dict[str, Any]:
        """Verify an MCP execution trace under an execution policy and return the run record.

        trace: the MCP session as JSON-RPC messages (JSON Lines).
        policy: the execution policy, as YAML/JSON text or a path.
        Returns the gate (ALLOW/REVIEW/DENY), any breaches, and the signed run record.
        """
        return tools.verify_execution(
            trace,
            policy,
            run_id=run_id,
            system=system,
            system_version=system_version,
            started_at=started_at,
        )

    @server.tool(name="verify_records")
    def verify_records(records: str) -> dict[str, Any]:
        """Verify a log of records offline: every hash, every link, every signature.

        records: the JSON Lines text of an answer-record or run-record log.
        Returns {"ok", "verified", "kind"}; fails if any record or link was altered.
        """
        return tools.verify_records(records)

    return server


def run() -> None:
    """Run the server over stdio. This is the console-script entry point."""
    build_server().run()
