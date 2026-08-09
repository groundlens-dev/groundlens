# Groundlens

**Groundlens checks what an answer tells people they have to do.**

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

There is no score, no confidence and no threshold. A number between zero and one invites somebody to move the line later, and a control whose line moves is not a control.

## What it checks

Eight kinds of statement, each returned with the exact character span it came from.

| Kind | What it picks up |
|---|---|
| Obligation | must, must not, may, need not, should |
| Deadline | within 14 days, by 31 March, before closing |
| Date | absolute and relative dates |
| Duration | 30 days, six months, business days |
| Currency | amounts with a unit |
| Number | bare quantities |
| Percent | rates and percentage points |
| Citation | article, section and clause references |

Obligation polarity is the part no other tool ships. "The customer must notify us" and "the customer may notify us" are two different instructions, and the difference is invisible to a similarity score. Groundlens treats it as a typed, checkable statement, ranks the five strengths, and reports an answer that is firmer than the evidence behind it.

A rule pack adds the rest: required wording, forbidden wording, a required disclosure block, a citation that has to resolve to a source you actually passed, and context the caller has to declare. A missing declaration is a failure, not a silent pass.

## What it does not do

!!! warning "Groundlens does not measure truth"
    If a claim is wrong and every source agrees with it, Groundlens clears it. Truth needs a
    source of truth: a lookup, a register, a knowledge base or a person.

- It does not read prose for meaning. A defect stated in words it does not extract will pass.
- It does not cover the input side. Prompt injection, harmful content and jailbreaks are somebody else's job.
- It does not rank or grade. The output is clear or escalate, per rule, with a span.
- It only catches what a pack asks for. An empty pack clears everything.

## What this is not

Groundlens is narrow on purpose. If your problem is one of these, use the tool that was built for it. Every one of them is good.

| You need | Use | Why it is better at this |
|---|---|---|
| Which words in this answer are not supported by the retrieved text | [LettuceDetect](https://github.com/KRLabsOrg/LettuceDetect) | MIT, `pip install lettucedetect`, runs offline with no LLM, returns token level spans over the whole answer. This is the general groundedness job and it does it well. |
| A single number for how well a summary sticks to its source | [Vectara HHEM](https://huggingface.co/vectara/hallucination_evaluation_model) | An open model built and tuned for exactly that score. |
| Metrics over a test set while you tune a RAG pipeline | [RAGAS](https://github.com/explodinggradients/ragas), [DeepEval](https://github.com/confident-ai/deepeval) | Faithfulness, answer relevancy, context precision, dataset runners, CI reporting. |
| A managed service inside your cloud | [Azure AI Content Safety groundedness detection](https://learn.microsoft.com/azure/ai-services/content-safety/concepts/groundedness) | Hosted, supported, no weights to ship, covers input safety too. |
| Formal proof that a claim follows from an encoded policy | [AWS Bedrock Automated Reasoning checks](https://docs.aws.amazon.com/bedrock/latest/userguide/automated-reasoning.html) | Real logical verification against a policy model, with immutable numbered policy versions. |
| To measure how often a model hallucinates | [HalluLens](https://github.com/facebookresearch/HalluLens) | A benchmark, which is a different thing from a control in a live pipeline. |

Groundlens is not a hallucination detector and does not produce a factual consistency score.

## Install

```bash
pip install groundlens
```

The only runtime dependency is `pyyaml`. `import groundlens` does not import `torch`, `numpy`, `transformers` or `sentence_transformers`, and CI fails if it ever does.

The optional geometry work needs its own extra:

```bash
pip install "groundlens[geometry]"
```

## Rule packs

A pack is a YAML file, never Python. A reviewer who does not write code has to be able to read it, diff two versions of it, and sign the diff. Two ship with the library, `eu-retail-banking` and `decision-rationale`.

The identity of a pack is the SHA-256 of its bytes, taken before parsing. A version label is a string somebody typed. The hash is what binds to behaviour, and the hash is what the record stores.

Packs read numbers and dates through `locale_profile`, never through the environment.

## Audit

Every call returns a record next to the decision: hashes of the answer and of each source, the pack name, version and content hash, the counts, and every finding with its span. Metadata values never reach the record. Only the key names do, because the values may carry personal data.

Reruns of the same inputs under the same pack hash produce the same record, byte for byte. There is no floating point, no wall clock, no environment locale and no randomness in the path. Each row of `groundlens.audit.open_log` is hashed against the row before it, so a later edit to the trail is visible.

This is a property of the tool. It is not a claim about what any regulation requires of you.

## Where to go next

- New here: [Installation](getting-started/installation.md) and [Quickstart](getting-started/quickstart.md).
- Write your own rules: [Custom rule sets](guides/custom-rule-sets.md).
- Deploy it: [Banking deployment](guides/banking-deployment.md), [Data handling](guides/data-handling.md).
- Frameworks: [LangGraph](integrations/langgraph.md), [LangChain](integrations/langchain.md), [CrewAI](integrations/crewai.md), [Semantic Kernel](integrations/semantic-kernel.md), [AutoGen](integrations/autogen.md).
- Editor and chat: the [Groundlens MCP server](https://github.com/groundlens-dev/groundlens-mcp).

## Research

Geometry (SGI and DGI) is where Groundlens started. It measures where an answer sits relative to its question and its source, and it is a useful ranking signal when an answer ignores the document it was given. It is optional, it is not the product, and it sits behind `pip install "groundlens[geometry]"`.

It has a known limit, established in our own work: detectability tracks how closely a wrong answer matches the register of a right one. A wrong value written in exactly the right style is close to invisible to a single frozen sentence embedding. That result is the reason the product moved to typed statements and written rules.

Start at the [geometry quickstart](research/geometry-quickstart.md), then [SGI](concepts/sgi.md), [DGI](concepts/dgi.md), [Switch](concepts/switch.md) and [Calibration](concepts/calibration.md).

Five arXiv preprints. Each has been revised in response to reviews. None is a peer-reviewed publication.

- *Semantic Grounding Index: Geometric Bounds on Context Engagement in RAG Systems* (2025), [arXiv:2512.13771](https://arxiv.org/abs/2512.13771)
- *A Geometric Taxonomy of Hallucination in LLMs* (2026), [arXiv:2602.13224](https://arxiv.org/abs/2602.13224)
- *How Transformers Reject Wrong Answers: Rotational Dynamics of Factual Constraint Processing* (2026), [arXiv:2603.13259](https://arxiv.org/abs/2603.13259)
- *The Outer Geometry of Truth: Register Alignment and the Limits of Embedding-Based Hallucination Detection*, preprint
- *The Geometry of Validity*, preprint

The register-alignment result is the fourth of these. Its notebooks are not released yet. See [Benchmark results](benchmarks/results.md).
