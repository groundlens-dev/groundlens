---
name: groundlens
description: Check an answer against the user's own documents before sending it. Catches wrong figures, recomputes the arithmetic, and flags claims about the wrong company or person. Runs locally in milliseconds, no API key, no second model.
version: 1.0.0
metadata:
  openclaw:
    emoji: "🔎"
    homepage: https://groundlens.dev
    requires:
      bins:
        - groundlens
    install:
      - kind: uv
        package: groundlens
        bins: [groundlens]
---

# GroundLens: check the answer before you send it

Use this skill when you answer from documents the user gave you or that you
retrieved (reports, contracts, invoices, statements, regulations, notes) and
your answer contains **figures, dates, percentages, amounts or names**.

GroundLens compares your draft with those documents and returns one of three
decisions:

- **PASS**: every figure it could check is in the sources or follows from them.
- **FAIL**: a figure is contradicted, a calculation does not add up, or the
  answer talks about a different entity than the one asked about.
- **REVIEW**: it could not confirm something. Not proven wrong, not proven right.

It runs on the user's machine. No account, no API key, no network, no model.

## When to use it

- Before sending any answer that quotes numbers taken from documents.
- After you compute something from document figures (a total, a change, a
  ratio), to check the arithmetic.
- When the user asks about one company, person or product and the documents
  mention several.

Skip it for small talk, opinions, or answers with no figures and no documents.

## How to run it

Write the draft answer, the question and each source to files, then:

```bash
groundlens verify \
  --question question.txt \
  --answer answer.txt \
  --source report=annual_report.txt \
  --source notes=meeting_notes.txt
```

- Give every source an id (`report=`, `notes=`); the result cites it.
- Add `--scope entity="Acme Ltd"` when the question is about one entity.
- Add `--locale es` (or `de`, `fr`, ...) when the documents write numbers in
  that language's format, e.g. `41,2 millones`.
- Add `--json` to get the full record with every claim and its source.

Exit code: `0` PASS, `1` FAIL, `3` REVIEW, `2` error.

Example output:

```text
FAIL  policy=groundlens_default_v1  record=rec_ab201f0cf308_b0ced69fd71a
  c2   groundlens.numeric       contradicted  0.00  nearest in report: '€41.2 million'
  c5   groundlens.numeric       unsupported   0.00  nearest in report: '2025'
```

## What to do with the result

- **PASS**: send the answer.
- **FAIL**: do not send it as is. Read each reason, fix the figure using the
  value GroundLens found in the source, and verify again. If you cannot fix it,
  tell the user which figure you could not confirm.
- **REVIEW**: send the answer, but say plainly which figure or claim you could
  not confirm in their documents, so they can check it themselves.

Never present a FAIL or REVIEW answer as verified.

## Limits

GroundLens checks figures, arithmetic, who the answer is about, and whether it
answers the question. It does not judge the meaning of free text: a wrong
statement with no number in it will usually pass. Treat PASS as "no figure
problem found", not as "the answer is true".

## More

- Code and docs: https://github.com/groundlens-dev/groundlens
- Benchmark on public data: https://github.com/groundlens-dev/groundlens/blob/main/BENCHMARK.md
- MCP server (same checks as tools): `uvx --from "groundlens[mcp]" groundlens-mcp`
- Custom setups and calibration audits: https://groundlens.dev
