# Contributing

The library is about 1,100 lines. It stays that way on purpose. The last version
of this project reached 47,000 lines and almost none of it was load-bearing.

## Three rules that are not negotiable

**1. No number is published unless committed code regenerates it.**
Script, seed and pinned source revision, or it does not go in the README. This
is why v3 exists.

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

## GitHub Actions must be pinned to a SHA

Every `uses:` in `.github/workflows/` is pinned to a full 40-character commit
SHA with the version as a trailing comment:

```yaml
- uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8  # v5.0.1
```

A tag is a moving pointer. `@v4` today and `@v4` next month can be different
code, and that code runs with a token in your CI. Dependabot is configured to
bump these weekly, so pinning costs nothing ongoing.

To re-pin after editing a workflow:

```bash
npx pin-github-action .github/workflows/*.yml
```

CI will not enforce this — OpenSSF Scorecard will, and the badge is on the
README.

## Cutting a release

Releases are never made by hand. Tag and push; `.github/workflows/release.yml`
does the rest:

```bash
# bump __version__ in src/groundlens/__init__.py first — CI checks the tag matches
git tag v3.0.1 && git push origin v3.0.1
```

It builds the sdist and wheel **once**, then signs that exact artifact with
Sigstore, generates SLSA 3 provenance for it, attaches both to the GitHub
release, and publishes to PyPI with attestations via Trusted Publishing. Nothing
downstream rebuilds — rebuilding between signing and publishing would sign one
file and ship another.

A release uploaded through the web UI, or built locally and dragged in, is
unsigned and has no provenance. Don't.

## What will be declined

Framework integrations, agent helpers, rule engines, compliance decorators, a
docs site. All of those existed in v2. None of them had a measurement behind them.
