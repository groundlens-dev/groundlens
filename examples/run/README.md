<!--
SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
SPDX-License-Identifier: Apache-2.0
-->

# Verifying an agent run

An end-to-end example: an MCP execution trace, an execution policy, and one
command that turns them into a signed, offline-verifiable run record.

```bash
glv run verify \
  --trace examples/run/trace.jsonl \
  --policy examples/run/execution-policy.yaml \
  --run-id run_demo \
  --system invoice-agent \
  --log runs.jsonl
```

The trace has the agent call `shell.exec`, which the policy denies, so the run
record's `gate` is `DENY` and `glv` exits non-zero. Remove the last two lines of
the trace and the run is `ALLOW`.

Check the signed log at any time, offline:

```bash
glv run check runs.jsonl
```
