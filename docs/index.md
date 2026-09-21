```{image} assets/groundlens_header.png
:alt: GroundLens
:align: center
:width: 640px
```

# Execution verification runtime for AI systems and agents

GroundLens turns what an AI system does into evidence that someone else can
check. It reads an answer or a whole execution, runs a pipeline of verifiers
that each produce evidence rather than a verdict, lets a policy you control
turn that evidence into a decision, and seals the result in a signed,
hash-chained record mapped to the regulation it concerns.

It runs beside your system, not inside the model. It has no opinion of its
own: the verifiers measure, the policy decides, and every decision carries a
record that anyone can verify offline, on any machine, without calling
GroundLens back.

```{admonition} Who this is for
Teams that put AI in front of regulated decisions and have to show, later and
to someone else, that a given answer or action was checked, how it was
checked, and under which rule. Model risk, compliance, audit, and the
engineers who build the systems they sign off on.
```

## Start here

If you are new, install the package, verify one answer, then read the
[concepts](concepts/overview.md) to understand what the pieces mean.

```{code-block} bash
pip install groundlens
```

```{code-block} python
from groundlens import verify

record = verify(
    "The invoice total is 1,000 dollars.",
    [("invoice.pdf#p1", "The total amount due is 10,000 dollars.")],
    question="What is the invoice total?",
)
print(record.decision)      # FAIL
print(record.report())      # what a reviewer needs to see
record.verify()             # recompute every hash and the signature, offline
```

## The documentation

- **[Getting started](getting-started/installation.md)** — install, verify your
  first answer, and add the model bundle.
- **[Concepts](concepts/overview.md)** — verifiers, claims and evidence,
  policies, records, the execution runtime, determinism, and the EU AI Act
  mapping.
- **[Guides](guides/verify-an-answer.md)** — task-by-task walkthroughs, from
  verifying an answer to producing an evidence package for an auditor.
- **[Python API](reference/python-api.md)** — every public function and class,
  from the docstrings.
- **[Command line](reference/cli.md)** — the `groundlens` / `glv` commands.

```{toctree}
:hidden:
:caption: Getting started

getting-started/installation
getting-started/quickstart
getting-started/bundles
```

```{toctree}
:hidden:
:caption: Concepts

concepts/overview
concepts/verifiers
concepts/claims-and-evidence
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
guides/writing-policies
guides/rules
guides/calibration
guides/evidence-for-auditors
```

```{toctree}
:hidden:
:caption: Reference

reference/python-api
reference/cli
changelog
```
