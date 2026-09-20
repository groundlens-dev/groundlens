# Verify an answer

The core task: check a model's answer against the sources it was given, in any
language, and get a record you can keep. This guide goes past the quick start
into paraphrase, units and multiple languages.

## The shape of a call

```{code-block} python
from groundlens import verify

record = verify(
    answer,                       # the model output, a string
    [("doc#p1", source_text)],    # (id, text) pairs; the id is what the record cites
    question="...",               # what the model was asked; never a source
    locale="en",                  # how the documents write numbers
    policy="eu_ai_act_high_risk_v1",
    log="records.jsonl",          # optional: append the signed record
)
```

`record.decision` is `PASS`, `REVIEW` or `FAIL`. `record.report()` is the
reviewer's view: it shows only the claims that need a look, each next to the
source it lost to. See {func}`groundlens.verify` for every argument.

## Numbers are compared as quantities

Verification is not string matching. A paraphrase with the right numbers passes,
because the numeric verifier reads quantities, not text:

```{code-block} python
ok = verify(
    "Die Leitung ist 1,2 km lang; der Siedepunkt liegt bei 212 °F.",
    [("bericht", "Länge der Leitung: 1200 m. Siedepunkt: 100 °C.")],
    locale="de",
)
print(ok.decision)   # the km/m and °F/°C pairs agree
```

## The same mistake in five languages

The number format changes by language; the verdict does not. Reading `10.000`
as `1.000` is caught whether the source is English, German, French, Spanish or
Italian, as long as `locale` matches the documents.

```{code-block} python
cases = {
    "en": ("The total is 10,000 dollars.", "The invoice total is 1,000 dollars."),
    "de": ("Der Betrag beläuft sich auf 10.000 Euro.", "Der Betrag beträgt 1.000 Euro."),
    "es": ("El importe asciende a 10.000 euros.", "El importe es de 1.000 euros."),
}
for locale, (source, answer) in cases.items():
    r = verify(answer, [("doc", source)], locale=locale)
    print(locale, r.decision)      # FAIL in every language
```

## Words, when you have the bundle

With the `base` bundle installed, the lexical verifier also scores each content
word against the source that supports it, and the policy's threshold on that
score applies. Without the bundle, the answer is still fully checked on numbers
and rules. See [Bundles](../getting-started/bundles.md).

## The 3.x receipts API

`proofread()` gives the same word-level information as **receipts**: the weakest
anchors first, each next to the source word it lost to. It keeps its 3.x
signature. See {func}`groundlens.proofread`.

```{code-block} python
from groundlens import proofread

marks = proofread(answer, [("facture", source)], locale="fr", question=q, k=3)
print(marks.floor, marks.encoder_id)
print(marks.report())
```

A runnable, multi-language version of this is the first example notebook in the
repository, under `examples/notebooks/`.
