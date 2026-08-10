# Contributing

The library is about 1,100 lines. It stays that way on purpose. The last version
of this project reached 47,000 lines and almost none of it was load-bearing.

## Three rules that are not negotiable

**1. No number is published unless committed code regenerates it.**
Script, seed and pinned source revision, or it does not go in the README. This
is why v3 exists; see `RETRACTIONS.md`.

**2. No threshold, no `decision` field, no verdict.**
At 95% hallucination recall, no published method — including this one — reaches
a false-positive rate below 0.65 on any benchmark we have measured. A default cut
would ship a control that escalates most correct answers. `calibrate()` fits one
on the user's own data and hands back the cost. There is a test asserting the
result object has not grown a verdict; if you find yourself deleting it, stop.

**3. The core has zero runtime dependencies.**
A CI job reads the installed metadata and fails if that changes. Anything needing
numpy or torch belongs behind an extra.

## Before you open a PR

```bash
pip install -e ".[dev]"
pytest
ruff check src tests scripts && ruff format --check src tests scripts
mypy src
```

If you changed segmentation or numeral parsing, `tests/golden_structural.json`
will differ. Regenerate it with `python scripts/dump_fixture.py > tests/golden_structural.json`,
**read the diff**, and commit it deliberately. That diff is the mechanism, not a
chore — it is what catches a parser silently reading `3.14159` as `3.141` and `59`.

## Adding a numeral case

`scripts/dump_fixture.py` has a corpus at the top. Every line in it exists
because it broke something. Add lines; never remove them.

## What will be declined

Framework integrations, agent helpers, rule engines, compliance decorators, a
docs site. All of those existed in v2. None of them had a measurement behind them.
