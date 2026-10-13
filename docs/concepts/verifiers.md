# Verifiers

A verifier is a function that takes the verification input and produces
**evidence** about one or more claims. It never returns truth, and it never
decides. Every verifier, built-in or your own, follows the same contract:
`input → evidence`.

Each verifier declares a **determinism class** (see
[Determinism](determinism.md)) so a policy can refuse evidence that is not
reproducible enough to decide on.

## The built-in verifiers

| Id | Kind | What it checks | Determinism | Needs a bundle |
| --- | --- | --- | --- | --- |
| `groundlens.numeric` | exact | Numbers, currencies, percentages and physical units, compared as quantities in base units, with locale-aware parsing. | Exact | No |
| `groundlens.scope` | exact | Where each figure comes from: fails a figure found only in passages outside the request's scope (another company, contract or version). Runs when the request states a scope. See [Scope and provenance](scope.md). | Exact | No |
| `groundlens.rules` | symbolic | Your rule sets (YAML/JSON) run as checks. | Exact | No |
| `groundlens.lexical` | lexical/ML | Deprecated. Word-level grounding: each content word anchored to the source span that supports it, scored by a frozen multilingual encoder. | Reproducible | Yes (`base`) |
| `groundlens.nli` | ML | Deprecated. Entailment: each sentence-level statement checked against its sources by a three-way NLI classifier (entailment / neutral / contradiction). | Reproducible | Yes (a bundle carrying an entailment model) |
| `semantic.cosine` | statistical | Deprecated. Sentence similarity between each statement and its closest source passage, on the bundle's encoder. | Reproducible | Yes (`base`) |

```{admonition} The model channels are deprecated
:class: warning
`groundlens.lexical`, `groundlens.nli` and `semantic.cosine` run only when the
request names a bundle (`--bundle base`, `bundle="base"`), never by default,
and no shipped policy uses them. On real answers from annual reports,
contracts and a regulation they did not add value: the costly error is a real
figure attached to the wrong company, year or clause, and these channels check
that the words are present, not that they are bound to the right thing. They
leave the default build in the next release. The
[design page](../design/next.md) explains what replaces them.
```

## The numeric verifier in depth

`groundlens.numeric` is the workhorse and needs no model. It reads numbers the
way each language writes them and compares them as quantities, not strings:

- **Locales.** `10,000` (en) and `10.000` (de/es) are the same quantity; the
  `--locale` / `locale=` setting says which convention the documents use.
- **Scale words.** "ten thousand", "10K", "diez mil" and header-declared scales
  ("in millions of dollars") all normalise to base units.
- **Currencies, percentages, units.** `1,2 km` matches `1200 m`; `212 °F`
  matches `100 °C`; `37.35 billion` matches `37,350` under "in millions".
- **Two opt-in relaxations**, each noted in the receipt: `declared_precision`
  (accept a rounded figure) and `percent_as_fraction`.

A numeric mismatch is a **contradiction**, the strongest signal in the system,
and most policies map it straight to FAIL.

## Writing your own

A user-defined verifier is on the roadmap (5.2): a small interface, a declared
determinism class, recorded like any built-in, so your domain check joins the
same pipeline and lands in the same record. Adapters that run existing
detectors (for example Vectara HHEM or LettuceDetect) as verifiers are planned
alongside it.

See [Rules](../guides/rules.md) for the symbolic verifier you can use today
without writing code.
