# Command line

Installing the package gives you the `groundlens` command. It calls the same
engine as the Python API. Output is UTF-8 on every
platform.

```{admonition} Exit codes
:class: note

`0` PASS · `1` FAIL · `2` error · `3` REVIEW. A script can branch on the exit
code without parsing the output.
```

```{code-block} bash
groundlens --version
```

## verify

Verify an answer against its sources under a policy and print the record (or a
short summary).

```{code-block} bash
groundlens verify \
  --answer answer.txt \
  --source invoice.pdf#p1=invoice.txt \
  --question question.txt \
  --policy eu_ai_act_high_risk_v1 \
  --log records.jsonl
```

| Option | Meaning |
| --- | --- |
| `--answer PATH` | File with the model output. Required. |
| `--source id=path` | A source, repeatable. The `id` is what the record cites. |
| `--question PATH` | File with the question. Never a source. |
| `--policy NAME\|PATH\|YAML` | A built-in name, a file, or YAML. Default `groundlens_default_v1`. |
| `--rules PATH` | A rule set (JSON/YAML), repeatable. |
| `--locale CODE` | How the documents write numbers (`en`, `es`, `de`, …). Default `und`. A `locale` in the policy wins. |
| `--log PATH` | Append the signed record to this JSON Lines log. |
| `--signing-key HEX` | 32-byte hex Ed25519 seed (or `GROUNDLENS_SIGNING_KEY`). |
| `--no-units` | GroundLens 3.x bare-number semantics. |
| `--rounding RULE` | How a recomputed figure may differ from the one written: `within_last_digit` (default), `half_up`, `half_even`. A `rounding` in the policy wins. |
| `--no-derive` | Do not recompute figures from the answer's own supported figures. |
| `--scope key=value` | What the request is about (`--scope entity=UPS`), repeatable. Turns on the scope check. |
| `--provenance id:key=value` | Where a source comes from (`--provenance 10k#p114:entity=UPS`), repeatable. |
| `--risk-class NAME` | The risk class of the request, when the policy defines `risk_classes`. |
| `--json` | Print the full record instead of the summary. |

## report

Build an evidence package (report, auditor guide, records and hashes) from a
log.

```{code-block} bash
groundlens report records.jsonl --out evidence-package
```

| Option | Meaning |
| --- | --- |
| `log` | The JSON Lines records log. |
| `--out DIR` | Output directory. Default `report`. |

## record verify

Recompute every content hash, record hash, chain link and signature, offline.
Each file is one chain; a directory means every `.jsonl` file in it. With
several chains, every chain must verify and no record may be in two of them.

```{code-block} bash
groundlens record verify records.jsonl
groundlens record verify records/
groundlens record verify worker-1.jsonl worker-2.jsonl
```

## policy lint

Check a policy: reject unknown keys, unknown rounding rules and a required
verifier the engine does not have. Prints the hash of the resolved policy.

```{code-block} bash
groundlens policy lint my-policy.yaml
groundlens policy lint eu_ai_act_high_risk_v1
```

## policy show

Print a policy. With `--resolved`, print it with `extends` merged in and every
default written out, headed by the hash that goes into every record. Loading
the resolved text gives the same hash.

```{code-block} bash
groundlens policy show my-policy.yaml --resolved
```

## measure

Estimate the share of wrong answers among those that passed, from labels your
team puts on a sample. See [Measure and replay](../guides/measure-and-replay.md).

```{code-block} bash
groundlens measure records/ --sample 50 --seed 7          # the ids to label, no verdicts
groundlens measure records/ --labels labels.csv --seed 7 --out measurement.json
```

| Option | Meaning |
| --- | --- |
| `records` | Records logs or directories. Every chain is verified first. |
| `--sample N` | Print N record ids to label, drawn per decision and risk class. |
| `--seed N` | Seed for the sample, recorded in the report. |
| `--labels PATH` | CSV `record_id,label[,prediction]` or JSON Lines; `label` is `wrong` or `correct`. |
| `--review-minutes`, `--review-cost-per-hour`, `--error-cost` | Turn on the cost section. |
| `--signing-key HEX` | Seed for the report signature (or `GROUNDLENS_SIGNING_KEY`). |
| `--out PATH` | Write the signed report; default prints it. |

## replay

Check past traffic again under another policy and count the decisions that
would change. The judge's stored evidence is reused when it answered the same
prompt.

```{code-block} bash
groundlens replay --traffic traffic.jsonl --records records/ --policy new.yaml --out replay.json
```

## judge show-template

Print the exact prompt a [judge](../guides/use-a-judge.md) is sent for an
input, with the template id and the prompt hash that go into the record.
Nothing is sent anywhere. Takes the same `--answer`, `--source`,
`--question`, `--policy`, `--locale`, `--scope` and `--provenance` options as
`verify`; `--json` prints the prompt as JSON.

```{code-block} bash
groundlens judge show-template --answer a.txt --source 10k#p114=p114.txt --scope entity=UPS
```

## keygen

Print a fresh Ed25519 signing seed. Put it in `GROUNDLENS_SIGNING_KEY` so
records can be attributed to your application.

```{code-block} bash
export GROUNDLENS_SIGNING_KEY="$(groundlens keygen)"
```

## run verify, run check

Verify a whole agent execution instead of one answer. `run verify` turns a
trace (for example an MCP session, one JSON-RPC message per line) into a signed
run record and gates it under an execution policy: exit code `0` ALLOW, `1`
DENY, `3` REVIEW. `run check` verifies a run-record log offline.

```{code-block} bash
groundlens run verify --trace trace.jsonl --policy execution-policy.yaml \
  --run-id run_42 --system invoice-agent --log runs.jsonl
groundlens run check runs.jsonl
```

The same thing is available from Python as {func}`groundlens.verify_run`. See
[Verify an execution](../guides/verify-a-run.md).

## mcp

Run the [MCP server](../guides/mcp-server.md) over stdio. Needs the extra:
`pip install "groundlens[mcp]"`. The same as the `groundlens-mcp` command;
with nothing installed, `uvx --from "groundlens[mcp]" groundlens mcp`.

## glv: checking records without Python

Each [release](https://github.com/groundlens-dev/groundlens/releases) also has
`glv`, a single binary for Linux, macOS and Windows, for whoever checks the
records and does not run the application. It produces nothing; it only checks.

```{code-block} bash
glv record verify records.jsonl [more.jsonl | records/ ...]
glv run check runs.jsonl
glv policy lint my-policy.yaml
glv policy show eu_ai_act_high_risk_v1 --resolved
```

Exit code `0` when everything verifies, `2` when anything does not.
