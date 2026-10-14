```{image} assets/groundlens_header.png
:alt: GroundLens
:align: center
:width: 640px
```

# Guardrails for LLM answers

GroundLens checks an LLM answer against its sources without a model, decides
PASS, REVIEW or FAIL under your policy, and keeps a signed record.

It checks every figure against the passages the answer was written from, and
where each figure came from. A policy you own turns that evidence into a
decision, and the record of it is signed and stored before the decision
returns. Anyone can verify the records offline, with the public key alone. If
you already run an LLM judge, GroundLens runs first, and a FAIL never reaches
the judge.

```{admonition} Who this is for
Teams whose LLM answers carry figures from documents, in finance, credit,
insurance, legal or reporting, and who have to show later, to someone else,
that each answer was checked, how, and under which rule.
```

## Start here

```{code-block} bash
pip install groundlens
```

```{code-block} python
import groundlens as gl

verifier = gl.Verifier(sink=gl.sinks.jsonl("records/"))
record = verifier.check(
    answer="Revenue was €42.1 million.",
    passages=["Revenue reached €41.2 million."],
)
print(record.decision, record.reasons)
```

```{code-block} text
FAIL ['c2: groundlens.numeric contradicted: €42.1 million not in sources; nearest 41200000 EUR in ctx-0 (relative distance 0.021)']
```

No account, no API key, no model, no network. The signed record is in
`records/` before `check` returns. Then read the
[concepts](concepts/overview.md) to see what the pieces mean.

## The documentation

- **[Getting started](getting-started/installation.md)** — install, verify your
  first answer. No model is needed.
- **[Concepts](concepts/overview.md)** — verifiers, claims and evidence,
  policies, records, the execution runtime, determinism, and the EU AI Act
  mapping.
- **[Guides](guides/verify-an-answer.md)** — task-by-task walkthroughs, from
  verifying an answer to producing an evidence package for an auditor.
- **[Python API](reference/python-api.md)** — every public function and class,
  from the docstrings.
- **[Command line](reference/cli.md)** — the `groundlens` command, and `glv` for checking records without Python.
- **[Design](design/next.md)** — what changes in the next release and why, and what is built.

```{toctree}
:hidden:
:caption: Getting started

getting-started/installation
getting-started/quickstart
```

```{toctree}
:hidden:
:caption: Concepts

concepts/overview
concepts/verifiers
concepts/claims-and-evidence
concepts/scope
concepts/policies
concepts/records
concepts/runtime
concepts/determinism
concepts/eu-ai-act
```

```{toctree}
:hidden:
:caption: Guides

guides/verify-an-answer
guides/verify-a-run
guides/mcp-server
guides/writing-policies
guides/sign-and-store
guides/use-a-judge
guides/measure-and-replay
guides/observability
guides/rules
guides/evidence-for-auditors
```

```{toctree}
:hidden:
:caption: Reference

reference/python-api
reference/cli
changelog
```

```{toctree}
:hidden:
:caption: Design

design/next
```
