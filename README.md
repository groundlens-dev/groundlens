<div align="center">

# Groundlens

**Groundlens checks what an answer tells people they have to do.**

[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13%20|%203.14-blue?style=flat-square)](https://github.com/groundlens-dev/groundlens)
[![CI](https://img.shields.io/github/actions/workflow/status/groundlens-dev/groundlens/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/groundlens-dev/groundlens/actions)
[![PyPI](https://img.shields.io/pypi/v/groundlens?style=flat-square&label=version&color=orange)](https://pypi.org/project/groundlens/)
[![License: Apache](https://img.shields.io/badge/license-Apache%202-green?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![Docs](https://img.shields.io/badge/docs-docs.groundlens.dev-blue?style=flat-square)](https://docs.groundlens.dev)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/groundlens-dev/groundlens?style=flat-square&label=OpenSSF%20Scorecard)](https://scorecard.dev/viewer/?uri=github.com/groundlens-dev/groundlens)

[Docs](https://docs.groundlens.dev) · [Migrating from 1.x](MIGRATING.md) · [Rule packs](https://github.com/groundlens-dev/groundlens/tree/main/packs) · [MCP server](https://github.com/groundlens-dev/groundlens-mcp)

</div>

An answer written from your own documents can still turn a "may" into a "must", move a deadline, restate an amount that no source contains, or cite a section that does not exist. Those sentences are the ones that create an obligation for a customer, a claimant or a patient, and they are the ones a reviewer has to catch.

Groundlens pulls those statements out of the answer, compares each one against the sources you supplied and the rules you wrote, and returns one of two decisions: clear, or send this to a person. It runs on your machine. It calls no model. The same inputs give the same decision tomorrow.

## A first check

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

Two decisions and nothing else. There is no score, no confidence and no threshold, because a number between zero and one invites somebody to move the line later, and a control whose line moves is not a control.

## What it checks

Groundlens reads eight kinds of statement out of an answer, each with the exact character span it came from.

| Kind | What it picks up | Example of a finding |
|---|---|---|
| Obligation | must, must not, may, need not, should | The answer says "must" where the source says "may" |
| Deadline | within 14 days, by 31 March, before closing | The answer shortens a deadline the source gives |
| Date | absolute and relative dates | The answer states a date no source contains |
| Duration | 30 days, six months, business days | The answer counts business days as calendar days |
| Currency | amounts with a unit | The answer states an amount the source contradicts |
| Number | bare quantities | The answer states a figure no source contains |
| Percent | rates and percentage points | The answer confuses a rate with percentage points |
| Citation | article, section and clause references | The answer cites a section nobody supplied |

Obligation polarity is the part no other tool ships. "The customer must notify us" and "the customer may notify us" are two different instructions, and the difference is invisible to a similarity score. Groundlens treats it as a typed, checkable statement, ranks the five strengths, and reports an answer that is firmer than the evidence behind it.

On top of that, a rule pack can require named wording, forbid named wording, require a disclosure block, require a citation to resolve to a source you actually passed, and require the caller to declare context such as the product type. A missing declaration is a failure, not a silent pass.

## What it does not do

- It does not score truth. If a claim is wrong and every source agrees with it, Groundlens will clear it.
- It does not read prose for meaning. A defect stated in words it does not extract will pass.
- It does not cover the input side. Prompt injection, harmful content and jailbreaks are somebody else's job.
- It does not rank or grade. The output is clear or escalate, per rule, with a span.
- It only catches what a pack asks for. An empty pack clears everything.

## What this is not

Groundlens is narrow on purpose. If your problem is one of these, use the tool that was built for it. Every one of them is good.

| You need | Use | Why it is better at this |
|---|---|---|
| Which words in this answer are not supported by the retrieved text | [LettuceDetect](https://github.com/KRLabsOrg/LettuceDetect) | MIT, `pip install lettucedetect`, runs offline with no LLM, returns token level spans over the whole answer. This is the general groundedness job and it does it well. |
| A single number for how well a summary sticks to its source | [Vectara HHEM](https://huggingface.co/vectara/hallucination_evaluation_model) | An open model built and tuned for exactly that score, with a public leaderboard behind it. |
| Metrics over a test set while you tune a RAG pipeline | [RAGAS](https://github.com/explodinggradients/ragas), [DeepEval](https://github.com/confident-ai/deepeval) | Faithfulness, answer relevancy, context precision, dataset runners, CI reporting. Groundlens has none of that. |
| A managed service inside your cloud | [Azure AI Content Safety groundedness detection](https://learn.microsoft.com/azure/ai-services/content-safety/concepts/groundedness) | Hosted, supported, no weights to ship, covers input safety too. |
| Formal proof that a claim follows from an encoded policy | [AWS Bedrock Automated Reasoning checks](https://docs.aws.amazon.com/bedrock/latest/userguide/automated-reasoning.html) | Real logical verification against a policy model, with immutable numbered policy versions. |
| To measure how often a model hallucinates | [HalluLens](https://github.com/facebookresearch/HalluLens) | A benchmark, which is a different thing from a control in a live pipeline. |

Groundlens is not a hallucination detector and does not produce a factual consistency score. Nothing here replaces the tools above. Several teams will want Groundlens next to one of them, not instead of one.

## Install

```bash
pip install groundlens
```

The install is small. The only runtime dependency is `pyyaml`. `import groundlens` does not import `torch`, `numpy`, `transformers` or `sentence_transformers`, and there is a test in CI that fails if it ever does.

The geometry work described under [Research](#research) is optional and lives behind an extra:

```bash
pip install "groundlens[geometry]"
```

Coming from 1.x, read [MIGRATING.md](MIGRATING.md) first. `check()` now means something different.

## Rule packs

A pack is a YAML file, never Python. A reviewer who does not write code has to be able to read it, diff two versions of it, and sign the diff.

```yaml
pack: eu-retail-banking
version: 1.3.0
locale_profile: eu-es
requires_metadata:
  - product_type
  - disclosure_set
rules:
  - id: BNK-001
    description: Every monetary amount stated must appear in the evidence.
    assert: all_facts_matched
    where: { kind: currency }
    severity: fail
    citation: "EBA/GL/2020/06 §4.2"

  - id: BNK-020
    description: Obligation strength must not exceed the evidence.
    assert: obligation_polarity_consistent
    severity: fail
```

Eight assertions are supported and no others: `all_facts_matched`, `no_contradicted_facts`, `absent_lexicon`, `present_lexicon`, `obligation_polarity_consistent`, `citations_resolve`, `metadata_equals` and `predicate`. Adding a ninth is a change to the interface, not a change to a pack.

Two packs ship with the library, `eu-retail-banking` and `decision-rationale`. Point `ruleset=` at a name, at a path to your own `pack.yaml`, or at a `Pack` you loaded yourself.

```python
from groundlens import load_pack

pack = load_pack("packs/eu-retail-banking/pack.yaml")
print(pack.name, pack.version, pack.content_sha256[:12])
```

The identity of a pack is the SHA-256 of its bytes, taken before parsing. A version label is a string somebody typed. The hash is what binds to behaviour, and the hash is what the record stores.

Packs read numbers and dates through `locale_profile`, never through the environment. `1.000,50` is read the Spanish way under `eu-es` on a machine whose locale says otherwise.

## Audit

Every call returns a record alongside the decision. It carries hashes of the answer and of each source, the pack name, version and content hash, the counts, and every finding with its span.

```python
from groundlens.audit import open_log

with open_log("audit.db") as log:
    log.record_v2(identifier="case-4471", record=result.audit)
    print(log.verify_chain().valid)
```

Metadata values never reach the record. Only the key names do, because the values may carry personal data.

Two properties follow from the design rather than from a promise. Reruns of the same inputs under the same pack hash produce the same record, byte for byte, because there is no floating point, no wall clock, no environment locale and no randomness in the path. And each log row is hashed against the row before it, so a later edit to the trail is visible.

This is a property of the tool. It is not a claim about what any regulation requires of you.

## Research

Geometry (SGI and DGI) is where Groundlens started. It measures where an answer sits relative to its question and its source, and it is a useful ranking signal when an answer ignores the document it was given. It is now optional, it is not the product, and it sits behind `pip install "groundlens[geometry]"`.

It has a known limit, established in our own work: detectability tracks how closely a wrong answer matches the register of a right one. A wrong value written in exactly the right style is close to invisible to a single frozen sentence embedding. That result is the reason the product moved to typed statements and written rules.

Five arXiv preprints. Each has been revised in response to reviews. None is a peer-reviewed publication.

| # | Paper | ID |
|---|-------|-----|
| 1 | Semantic Grounding Index: Geometric Bounds on Context Engagement in RAG Systems | [arXiv:2512.13771](https://arxiv.org/abs/2512.13771) |
| 2 | A Geometric Taxonomy of Hallucination in LLMs | [arXiv:2602.13224](https://arxiv.org/abs/2602.13224) |
| 3 | How Transformers Reject Wrong Answers | [arXiv:2603.13259](https://arxiv.org/abs/2603.13259) |
| 4 | The Outer Geometry of Truth | preprint |
| 5 | The Geometry of Validity | preprint |

Geometry documentation lives under [docs/research](docs/research/).

## Open core

This repository is Apache-2.0. The pieces that tend to matter in a regulated deployment are not all inside a `pip install`: maintained domain packs with frozen canary suites, the evidence a second line of defence asks for, and integration templates with stage ordering and logging already wired. Write to javier@groundlens.dev.

## Citation

```bibtex
@software{marin_groundlens,
  author  = {Marin, Javier},
  title   = {Groundlens: deterministic checking of obligations, deadlines and figures in LLM output},
  url     = {https://github.com/groundlens-dev/groundlens},
  license = {Apache-2.0}
}
```

## Contributing

Issues and pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Contact: javier@groundlens.dev
