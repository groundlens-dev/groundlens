# GroundLens for Claude Code, Codex and OpenClaw

Before your assistant sends you an answer with figures taken from your documents, it checks
the draft with GroundLens:

- **PASS**: every figure it could check is in your documents or follows from them. The answer goes out.
- **FAIL**: a figure is wrong, does not add up, or belongs to another company. The assistant fixes it from the source and checks again.
- **REVIEW**: something could not be confirmed. The answer goes out, saying which figure.

It runs on your machine in a few milliseconds. No account, no API key, no second model.

## What is inside

- **The skill** `groundlens`: tells the assistant when to check (answers with figures, dates,
  amounts or names taken from documents) and what to do with each result.
- **The MCP server** `groundlens`: three tools, all read-only. `verify_answer` checks an
  answer against its sources; `verify_run` checks an agent's tool calls against a policy;
  `verify_records` checks a log of signed records.

## Install

You need [uv](https://docs.astral.sh/uv/) (it runs the server with `uvx`).

**Claude Code**

```bash
claude plugin marketplace add groundlens-dev/groundlens
claude plugin install groundlens@groundlens
```

**Codex**

```bash
codex mcp add groundlens -- uvx --from "groundlens[mcp]" groundlens mcp
```

**OpenClaw**

```bash
clawhub install groundlens
```

## Limits

GroundLens checks figures, arithmetic, who a figure belongs to and whether the answer
addresses the question. It does not judge the meaning of free text: a wrong sentence with
no figures will usually pass. PASS means "no figure problem found", not "true".

## Privacy

Everything runs locally. The plugin sends nothing anywhere: the MCP server reads the answer
and the sources the assistant passes to it, and returns a result. It keeps no data, has no
telemetry, and makes no network calls. The only download is the `groundlens` package and its
dependencies from PyPI when `uvx` first starts the server. Their exact versions and hashes
are in `uv.lock` (from `pyproject.toml`). Questions: javier@groundlens.dev.

## More

- Try it in the browser: <https://huggingface.co/spaces/groundlens/groundlens>
- Code and benchmark: <https://github.com/groundlens-dev/groundlens>
- Custom setups and calibration audits: <https://groundlens.dev>

Apache-2.0.
