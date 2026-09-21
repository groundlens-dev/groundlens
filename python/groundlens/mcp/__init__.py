# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""GroundLens MCP server: verification as tools an agent can call.

The verification logic lives in :mod:`groundlens.mcp.tools` (no MCP dependency).
The server itself (:mod:`groundlens.mcp.server`) needs the MCP SDK, installed with
``pip install 'groundlens[mcp]'``.
"""

from __future__ import annotations


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    from groundlens.mcp.server import run

    run()


__all__ = ["main"]
