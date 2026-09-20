# The execution runtime

An answer is one output. An **execution** is everything an agent or system did
to produce it: the model calls, the retrievals, the tool requests and their
results, the actions it took, the human approvals it waited for. The runtime
verifies the execution, under the same contract as an answer: an input produces
evidence, a policy decides, a signed record captures both.

## The run and its event log

A `VerificationRun` is recorded as an ordered, **hash-chained event log**. Each
event — a model call, a retrieval, a tool request, a tool result, a state read
or write, a human approval, an action, a policy decision — is appended in order
and linked to the one before it. What the log stores of the world is **hashes,
not content**: it can show that a tool was called with certain arguments and
returned a certain result without keeping the arguments or the result
themselves. The log is pure data — no I/O, no network.

## The gate

An **execution policy** is a list of ordered rules that decides `ALLOW`,
`REVIEW` or `DENY` for a tool call or an action. First match wins, with a
default when nothing matches. Rules match on the tool (and optionally the
server), the action (operation), or a minimum risk class.

```{code-block} yaml
id: agent_execution_v1
rules:
  # A shell tool is never allowed, whatever server offers it.
  - id: no-shell
    match: tool
    name: shell.exec
    effect: DENY
  # Any action at or above high risk needs a human approval.
  - id: high-risk-needs-human
    match: risk_at_least
    risk: high
    effect: REVIEW
default: ALLOW
```

Rules are tried in order; the first that matches decides. `match` is `tool`
(with `name` and optional `server`), `action` (with `operation`), `risk_at_least`
(with `risk`), or `any`. `default` applies when nothing matches.

`audit_run` rolls a finished run up to its strictest outcome and flags
**breaches**: an action executed under a `DENY` rule, or an action that needed a
human approval that never came. So the gate does two jobs — it decides per event
as the run happens, and it audits the whole run afterwards.

## Where a run comes from: the MCP adapter

The MCP adapter turns a real
[Model Context Protocol](https://modelcontextprotocol.io) session into a run. It
ingests the JSON-RPC messages off a transport (`tools/call` and its result,
`sampling/createMessage`), correlates each request with its response, and
records hashes of the arguments and results — never the content. The result is a
run you can gate and seal.

```{admonition} Record today, enforce later
The 5.0 adapter **observes** a trace and audits it. Standing in the execution
path to gate calls in flight — an MCP proxy or gateway that enforces — is on the
roadmap. The contracts are the same either way.
```

## The run record

`seal_run` seals a finished run into a signed, hash-chained **run record** with
the same Ed25519, offline-verifiable guarantee as an answer record.
`verify_run_record`, `verify_run_chain` and `verify_run_against_record` check
it. Answer records and run records share the same signing envelope, so a log can
hold both.

## From Python and the command line

```{code-block} python
from groundlens import verify_run, RunRecord
record = verify_run(trace="trace.jsonl", policy="execution-policy.yaml")
print(record.gate)          # ALLOW / REVIEW / DENY
```

```{code-block} bash
glv run verify --trace trace.jsonl --policy execution-policy.yaml --log run.jsonl
glv run check run.jsonl
```

Exit codes are `0` / `3` / `1` on `ALLOW` / `REVIEW` / `DENY`. See
[Verify an execution](../guides/verify-a-run.md) for a full walkthrough and
{func}`groundlens.verify_run`.
