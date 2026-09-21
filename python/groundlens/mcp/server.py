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
    server = MCPServer(
        "groundlens",
        instructions=(
            "GroundLens verifies AI output and executions and seals signed, "
            "offline-verifiable evidence records. Use verify_answer to check an "
            "answer against its sources under a policy, verify_run to gate an MCP "
            "execution trace, and verify_records to check a records log offline."
        ),
    )

    @server.tool(name="verify_answer")
    def verify_answer(
        answer: str,
        sources: list[Any],
        question: str | None = None,
        locale: str = "und",
        policy: str | None = None,
    ) -> dict[str, Any]:
        """Verify an answer against its sources under a policy and return the sealed record.

        sources: (id, text) pairs, {"id","text"} dicts, or bare strings.
        policy: a built-in name (e.g. "eu_ai_act_high_risk_v1"), a path, or YAML.
        Returns the decision (PASS/REVIEW/FAIL), the evidence, the regulatory
        mapping and the record with its content hash.
        """
        return tools.verify_answer(answer, sources, question=question, locale=locale, policy=policy)

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
