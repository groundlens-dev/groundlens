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
| `groundlens.rules` | symbolic | Your rule sets (YAML/JSON) run as checks. | Exact | No |
| `groundlens.lexical` | lexical/ML | Word-level grounding: each content word anchored to the source span that supports it, scored by a frozen multilingual encoder. | Reproducible | Yes (`base`) |
| `groundlens.nli` | ML | Entailment: each sentence-level statement checked against its sources by a three-way NLI classifier (entailment / neutral / contradiction). | Reproducible | Yes (a bundle carrying an entailment model) |

```{admonition} groundlens.nli and the model
`groundlens.nli` is wired into the engine and runs whenever the loaded bundle
carries an entailment model. The `base` bundle today ships the encoder for the
lexical channel; the entailment model ships in a later bundle. Until then the
verifier is present but does not run, and the shipped policies tolerate
unresolved statements so decisions are unchanged.
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
