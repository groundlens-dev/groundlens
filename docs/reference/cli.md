# Command line

Installing the package gives you two identical commands, `groundlens` and
`glv`. They call the same engine as the Python API. Output is UTF-8 on every
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
| `--bundle DIR\|NAME` | Deprecated. Run the lexical, entailment and similarity channels from this bundle. Without it no model runs, even when a bundle is installed. |
| `--no-lexical` | With `--bundle`, skip its channels. |
| `--log PATH` | Append the signed record to this JSON Lines log. |
| `--signing-key HEX` | 32-byte hex Ed25519 seed (or `GROUNDLENS_SIGNING_KEY`). |
| `--no-units` | GroundLens 3.x bare-number semantics. |
| `--rounding RULE` | How a recomputed figure may differ from the one written: `half_up` (default), `half_even`, `within_last_digit`. A `rounding` in the policy wins. |
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

Check a policy: reject unknown keys, thresholds on exact verifiers, guard bands
narrower than twice the verifier tolerance, unknown rounding rules and unknown
verifier ids. Prints the hash of the resolved policy.

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

## bundle

Manage model bundles. `pull` is the only command that uses the network.

```{code-block} bash
groundlens bundle pull base          # download and install (~470 MB, once)
groundlens bundle status             # is it installed, where, which hash
groundlens bundle verify path/       # re-hash every artefact
groundlens bundle build path/ --name base --bundle-version 1
```

| Command | Meaning |
| --- | --- |
| `bundle pull [NAME]` | Download and install a published bundle. `--into`, `--url`, `--sha256`, `--trust-unpinned`. |
| `bundle status [NAME]` | Whether a bundle is installed, its path and hash. |
| `bundle verify ROOT` | Re-hash every artefact of a bundle directory. |
| `bundle build ROOT` | Write `manifest.json`. `--name`, `--bundle-version` required. |

## keygen

Print a fresh Ed25519 signing seed. Put it in `GROUNDLENS_SIGNING_KEY` so
records can be attributed to your application.

```{code-block} bash
export GROUNDLENS_SIGNING_KEY="$(groundlens keygen)"
```

## Verifying an execution

The standalone `glv` binary shipped with each release adds a `run` command for
execution traces:

```{code-block} bash
glv run verify --trace trace.jsonl --policy execution-policy.yaml --log run.jsonl
glv run check run.jsonl
```

`glv run verify` turns a trace (for example an MCP session) into a signed run
record and gates it; `glv run check` verifies a run-record log offline. The
same thing is available from Python as {func}`groundlens.verify_run`. See
[Verify an execution](../guides/verify-a-run.md).
