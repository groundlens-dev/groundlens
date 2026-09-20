# Evidence for auditors

This guide covers the part of GroundLens a compliance officer, an internal
auditor or a customer's risk team touches: a log of verifications, checked
offline, turned into a package they can read and re-verify without you.

The second example notebook in the repository (`examples/notebooks/`) runs this
end to end.

## 1. An application writes a log

Each answer is verified under a policy and appended to a JSON Lines log, signed
with the application's own key so records can be attributed to it.

```{code-block} python
import os
from pathlib import Path
from groundlens import verify

os.environ["GROUNDLENS_SIGNING_KEY"] = my_seed_hex   # a stable key per application
log = Path("records.jsonl")

for question, answer in exchanges:
    verify(answer, sources, question=question,
           policy="eu_ai_act_high_risk_v1", log=log)
```

## 2. Verify the whole chain, offline

An auditor receives `records.jsonl` and nothing else. Verification recomputes
every content hash, every record hash, every link and every signature. It needs
no key material: the public key travels inside each record.

```{code-block} python
from groundlens import Record

records = Record.read_log(log)
print(Record.verify_chain(records), "records verified")
```

```{code-block} bash
groundlens record verify records.jsonl
```

## 3. Tampering is detected

Editing a record breaks its content hash; removing a record from the middle
breaks the next record's back-link. Either way `verify_chain` raises.

```{code-block} python
from groundlens.record import IntegrityError
# change a decision by hand, then:
try:
    Record.from_json(edited).verify()
except IntegrityError as e:
    print("rejected:", e)
```

## 4. The regulatory mapping is in the record

Each record carries the policy id, the policy hash and the mapping that was in
force, next to the decision it applies to. So a FAIL is not just a FAIL: it is a
FAIL tied to, for example, Article 15(1). See
[EU AI Act mapping](../concepts/eu-ai-act.md).

## 5. Produce the evidence package

`groundlens report` turns a log into the files an auditor actually reads:

```{code-block} bash
groundlens report records.jsonl --out evidence-package
```

It writes `report.md` (decisions, reasons, verifiers, policy and bundle hashes),
`report.json` (the same, for tooling), a copy of `records.jsonl`, and
`README-auditor.md`, a one-page explanation of how to verify the package
independently.

## What an auditor can rely on

- **Integrity** — any change to a record, or to the order of the log, is
  detected offline by anyone with the file.
- **Attribution** — each record is signed; the public key is inside it.
- **Reproducibility** — the same input, policy and bundle give the same content
  hash on any machine; exact verifiers are bit-identical, statistical verifiers
  run pinned models with declared tolerances and guard bands.
- **Separation of duties** — the engine measured, the policy decided, and the
  policy is named and hashed in every record.
