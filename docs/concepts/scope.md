# Scope and provenance

An answer can quote a real figure and still be wrong, because the figure
belongs to something else: another company, another contract, another version
of a policy. This is the costly error we measured most often on real retrieval
systems. When a retriever is not filtered by company, it returns passages from
other companies' annual reports, and the model takes their figures. Every
figure exists in some source, so a check that only asks "is this number in the
sources?" passes the answer.

Scope and provenance close that gap.

- **Scope** says what the request is about: `entity = AAPL`,
  `contract = P-1001`, `contract_version = 3`. Your application knows it: the
  customer on screen, the contract the user opened, the company the analyst is
  looking at.
- **Provenance** says where each passage comes from: the same keys, set by your
  retrieval layer, plus any you find useful (`doc_id`, `page`, `sha256`).

```{code-block} python
from groundlens import verify

record = verify(
    "The 2006 tax expense was $1.9 billion.",
    [
        ("IP/2007/page_75", "The company recorded an income tax provision of $1.9 billion.",
         {"entity": "IP"}),
        ("AAPL/2006/page_100", "Provision for income taxes was $829 million.",
         {"entity": "AAPL"}),
    ],
    scope={"entity": "AAPL"},
    locale="en",
)
record.decision   # FAIL: $1.9 billion comes only from International Paper's report
```

From the command line:

```{code-block} bash
glv verify --answer answer.txt \
  --source IP#75=ip.txt --source AAPL#100=aapl.txt \
  --provenance IP#75:entity=IP --provenance AAPL#100:entity=AAPL \
  --scope entity=AAPL --policy policies/eu_ai_act_high_risk_v1.yaml --locale en
```

## What the scope check does

When a request states a scope, the `groundlens.scope` verifier runs. It is
`exact`: no model, the same result on every machine. For each figure in the
answer it finds every passage where the same number appears and reports:

| where the figure appears | evidence | in the shipped policies |
|---|---|---|
| in at least one passage inside the scope | `supported` | no effect |
| only in passages outside the scope | `contradicted`, note `out_of_scope_source` | FAIL |
| only in passages that do not state their provenance | `unsupported`, note `provenance_missing` | REVIEW |
| in no passage | nothing; the numeric verifier speaks to it | — |

A passage is inside the scope when every scope key its provenance states has
the same value as the request. A passage that states none of the scope keys
has unknown provenance. Figures are located by their number alone, ignoring
scale words and units, because tables often state "in millions" once in a
header while the answer repeats it. Whether the figure is the right one is the
numeric verifier's question; where it comes from is this one's.

The receipt names the passage the figure came from, so a reviewer opens the
right page.

## What it does not do

- It does not replace access control. Your retrieval layer should only return
  passages the user may see. The scope check is a second, independent line:
  it records where each figure came from and fails the answer when a figure
  crossed the boundary.
- It does not check words or sentences yet, only figures.
- It cannot catch a correct figure taken from the wrong row of a passage that
  is inside the scope. That needs a reader of the passage, such as a judge.

## In the record

The scope and the provenance of every passage are part of the verification
input, so they are covered by the record's `input_hash`. Change the scope and
the hash changes. A request without a scope produces exactly the record it
produced before this check existed.
