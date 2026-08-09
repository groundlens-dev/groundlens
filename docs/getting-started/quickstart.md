# Quickstart

One call, one decision, one record. This page takes you from `pip install` to a rule pack of your own.

```bash
pip install groundlens
```

## Your first check

`check()` takes the answer, the sources it was supposed to use, and a rule pack.

```python
from datetime import date
from groundlens import check

result = check(
    "You must call us before you travel abroad. The annual fee is 45,00 EUR.",
    [{"id": "terms.pdf#p2", "text": "The customer may repay the balance early. The annual fee is 30,00 EUR."}],
    ruleset="eu-retail-banking",
    metadata={"product_type": "credit-card", "disclosure_set": "es-2026"},
    reference_date=date(2026, 8, 8),
)
print(result.decision.value)
for finding in result.findings:
    if finding.severity.value == "fail":
        print(finding.rule_id, finding.message)
```

```text
escalate
BNK-001 The answer says '45,00 EUR' but the source says 'EUR 30'.
BNK-031 Required disclosure block present.
BNK-020 The answer tells the reader 'You must call us before you travel abroad', and no source says that.
```

Three things happened. The amount in the answer disagrees with the amount in the source. The answer created an obligation for the reader that nothing in the sources supports. And a disclosure the pack requires is not there.

`result.decision` is `Decision.CLEAR` or `Decision.ESCALATE`. There is nothing in between.

## Every source needs an id

```python
[{"id": "terms.pdf#p2", "text": "..."}]
```

A bare string is rejected. Ids are yours to choose and they should be stable, because a finding points at one, and the person who reviews the case has to open it.

## Declare your context, or the check fails

A pack can require the caller to supply named context. If it is missing, the decision is `ESCALATE` and the reason says so. There is no flag to turn this off.

The `mypack.yaml` used here and below is the one written out under [Write your own pack](#write-your-own-pack).

```python
from groundlens import check

result = check(
    "The fee is 30,00 EUR.",
    [{"id": "s1", "text": "The fee is 30,00 EUR."}],
    ruleset="mypack.yaml",
)
print(result.decision.value)
for finding in result.findings:
    print(finding.severity.value, finding.code, finding.message)
```

```text
escalate
fail pack.metadata.missing The rule pack 'house-style' needs the caller to supply 'case_id', and it was not supplied. Nothing was checked against it, so this answer has to be reviewed by a person.
```

Supply it and the same answer clears.

```python
result = check(
    "The fee is 30,00 EUR.",
    [{"id": "s1", "text": "The fee is 30,00 EUR."}],
    ruleset="mypack.yaml",
    metadata={"case_id": "4471"},
)
print(result.decision.value, len(result.findings))
```

```text
clear 0
```

## Dates come from you, not from the clock

If a pack reads relative dates, pass `reference_date` as a `date` or an ISO string. `date.today()` is not called anywhere in this path, so a case checked today gives the same answer when it is re-checked next year.

## Write your own pack

A pack is a YAML file. Save this as `mypack.yaml` and point `ruleset=` at the path.

```yaml
pack: house-style
version: 0.1.0
locale_profile: eu-es
requires_metadata:
  - case_id
rules:
  - id: HS-001
    description: Every monetary amount stated must appear in the evidence.
    assert: all_facts_matched
    where: { kind: currency }
    severity: fail

  - id: HS-002
    description: Obligation strength must not exceed the evidence.
    assert: obligation_polarity_consistent
    severity: fail

  - id: HS-003
    description: No decision language.
    assert: absent_lexicon
    lexicon: ["we have decided", "your application is approved"]
    severity: fail
```

`locale_profile` decides how numbers and dates are read. Under `eu-es`, `1.000,50` is one thousand and a half, whatever the machine's own locale says.

Eight assertions are available and no others: `all_facts_matched`, `no_contradicted_facts`, `absent_lexicon`, `present_lexicon`, `obligation_polarity_consistent`, `citations_resolve`, `metadata_equals` and `predicate`.

## Read the findings

Each finding carries a stable code, a severity, a message written for a person, and, where there is one, the character span in the answer it came from.

```python
from groundlens import check

result = check(
    "The fee is 45,00 EUR.",
    [],
    ruleset="mypack.yaml",
    metadata={"case_id": "4471"},
)
for finding in result.findings:
    span = finding.fact.span if finding.fact else None
    print(finding.severity.value, finding.code, span, finding.message)
```

```text
warn evidence.empty None No sources were provided, so nothing in this answer could be compared against anything.
fail fact.unmatched.currency (11, 20) The answer states '45,00 EUR', which does not appear in any of the sources provided.
```

Spans index into the NFKC-normalised answer, not into the raw string you passed.

`FAIL` escalates. `WARN` and `INFO` are recorded and do not escalate on their own.

## Keep the record

```python
a = result.audit
print(a.answer_sha256[:16])
print(a.ruleset["name"], a.ruleset["version"], a.ruleset["content_sha256"][:12])
print(a.counts)
print(a.determinism)
print(a.metadata_keys)
```

```text
4e948e46f26b98a9
house-style 0.1.0 8ef7b57bf7b0
{'facts_extracted': 1, 'facts_matched': 0, 'facts_unmatched': 1, 'facts_contradicted': 0, 'rules_evaluated': 3, 'rules_failed': 1}
{'unicode_form': 'NFKC', 'locale_profile': 'eu-es', 'reference_date': None}
['case_id']
```

`metadata_keys` holds the key names. The values are never written, because they may carry personal data.

To keep a running trail, use the hash-chained log.

```python
from groundlens.audit import open_log

with open_log("audit.db") as log:
    log.record(
        identifier="case-4471",
        method="check",
        flagged=result.decision.value == "escalate",
        metadata={"ruleset": result.audit.ruleset, "counts": result.audit.counts},
    )
    print(log.verify_chain().valid)
```

## Next

- [Custom rule sets](../guides/custom-rule-sets.md) for the full pack format.
- [Banking deployment](../guides/banking-deployment.md) for a worked domain.
- [Geometry quickstart](../research/geometry-quickstart.md) for the optional SGI and DGI work.
