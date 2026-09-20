# Verify an execution

An answer is one output; an **execution** is the whole run behind it. This guide
turns a Model Context Protocol trace into a gated, signed run record. The
concepts are in [The execution runtime](../concepts/runtime.md).

There is a runnable version in the repository under `examples/run` (a trace, an
execution policy and a README).

## 1. The trace

A trace is JSON Lines of the JSON-RPC messages the session exchanged: model
calls (`sampling/createMessage`) and tool calls (`tools/call`) with their
results. Each line is one message.

```{code-block} json
{"jsonrpc":"2.0","id":1,"method":"sampling/createMessage","params":{"messages":[{"role":"user","content":"check the invoice total"}]}}
{"jsonrpc":"2.0","id":1,"result":{"model":"claude-x","role":"assistant","content":{"text":"the total is 10,000"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"crm.lookup","arguments":{"account":42}}}
{"jsonrpc":"2.0","id":2,"result":{"isError":false,"content":[{"type":"text","text":"ok"}]}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"shell.exec","arguments":{"cmd":"rm -rf /"}}}
```

GroundLens records **hashes** of arguments and results, not the content itself.

## 2. The execution policy

```{code-block} yaml
id: eu_high_risk_v1
rules:
  - id: no-shell
    match: tool
    name: shell.exec
    effect: DENY
  - id: high-risk-needs-human
    match: risk_at_least
    risk: high
    effect: REVIEW
default: ALLOW
```

## 3. Verify and gate

```{code-block} bash
glv run verify \
  --trace trace.jsonl \
  --policy execution-policy.yaml \
  --log run.jsonl

echo "exit: $?"       # 0 ALLOW · 3 REVIEW · 1 DENY
```

The `shell.exec` call matches the `no-shell` rule, so the run rolls up to DENY
and the audit flags the breach. From Python:

```{code-block} python
from groundlens import verify_run

record = verify_run(trace="trace.jsonl", policy="execution-policy.yaml")
print(record.gate)              # DENY  (ALLOW / REVIEW / DENY)
for b in record.breaches:
    print(b)
```

See {func}`groundlens.verify_run` for every argument.

## 4. Check a run record later

```{code-block} bash
glv run check run.jsonl
```

This recomputes every hash, link and signature in the run-record log, offline,
exactly as `record verify` does for answer records. Answer records and run
records share the same signing envelope, so one log can hold both.
