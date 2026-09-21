# MCP server

GroundLens ships an MCP server so an agent, or any
[Model Context Protocol](https://modelcontextprotocol.io) client (including
Claude), can call verification as a tool: check an answer, gate an execution, or
verify a log of records. It is a thin layer over the engine and runs over stdio.

This is the other side of the [runtime](../concepts/runtime.md): the runtime
*observes* an MCP session to verify it after the fact; the MCP server *is* a
server an agent calls, so verification becomes a step the agent can take itself.

## Install and run

The server is an optional extra, so the base package keeps its zero
dependencies.

```{code-block} bash
pip install "groundlens[mcp]"
groundlens-mcp            # runs the server over stdio
```

`python -m groundlens.mcp` runs the same server.

## The tools

```{list-table}
:header-rows: 1

* - Tool
  - What it does
* - `verify_answer`
  - Verify an answer against its sources under a policy. Returns the decision
    (`PASS` / `REVIEW` / `FAIL`), the evidence, the regulatory mapping and the
    signed record. Sources are `(id, text)` pairs, `{"id","text"}` dicts, or
    bare strings.
* - `verify_run`
  - Gate an MCP execution trace under an execution policy. Returns the gate
    (`ALLOW` / `REVIEW` / `DENY`), any breaches, and the signed run record.
* - `verify_records`
  - Verify a log of records offline: every hash, every link, every signature.
    Accepts answer-record and run-record logs.
```

## Connecting a client

An MCP client launches the server as a subprocess and talks to it over stdio.
The configuration looks the same across clients; the shape is:

```{code-block} json
{
  "mcpServers": {
    "groundlens": {
      "command": "groundlens-mcp"
    }
  }
}
```

If the command is not on the client's `PATH`, use the interpreter form:

```{code-block} json
{
  "mcpServers": {
    "groundlens": {
      "command": "python",
      "args": ["-m", "groundlens.mcp"]
    }
  }
}
```

Once connected, the client lists the three tools and can call them. For example,
an agent can call `verify_answer` on its own draft before returning it, and act
on a `FAIL`.

## What runs where

The server calls the same engine as the Python API and the `glv` binary, so a
verification through the server produces the same signed record as the same
verification anywhere else. The lexical and entailment channels still need a
[bundle](../getting-started/bundles.md); numbers and rules need nothing.
