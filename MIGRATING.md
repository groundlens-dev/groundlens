# Migrating from Groundlens 1.x to 2.0

Read this before you upgrade. Two things will break.

## 1. `check()` means something different

In 1.x, `check(score)` took a geometric score and turned it into a sentence a person could read.

In 2.0, `check()` is the product. It takes an answer, the sources behind it and a rule pack, and returns a decision.

| 1.x | 2.0 |
|---|---|
| `groundlens.check(score) -> Check` | `groundlens.geometry.render.render_check(score) -> Check`, not exported from the top level |
| not present | `groundlens.check(answer, evidence, *, ruleset, ...) -> Result` |

The new signature:

```python
check(
    answer: str,
    evidence: Sequence[Evidence] | Sequence[Mapping[str, str]],
    *,
    ruleset: str | Path | Pack,
    tools_output: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    reference_date: date | str | None = None,
) -> Result
```

A worked call:

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

Things to know about the new call:

- **Evidence needs ids.** A bare string is rejected. Every finding has to be able to point at the source a reviewer will open.
- **There is no score.** `Result` carries a decision, sorted findings and an audit record. `Decision.CLEAR` or `Decision.ESCALATE`, and nothing between them.
- **There is no clock.** If a pack reads relative dates, pass `reference_date`. `date.today()` is not called anywhere in this path.
- **Missing declared metadata fails.** If the pack lists a key under `requires_metadata` and you do not pass it, the decision is `ESCALATE` with `pack.metadata.missing`. There is no flag to turn that off.

## 2. Geometry is now an extra

SGI, DGI, calibration and the encoders pulled in `numpy` and `sentence-transformers`, which is roughly two gigabytes for a control that does not need them. They are now behind an extra.

```bash
pip install groundlens              # the control path. pyyaml only.
pip install "groundlens[geometry]"  # adds SGI, DGI, calibration, encoders.
```

`import groundlens` no longer imports `torch`, `numpy`, `transformers` or `sentence_transformers`, and CI fails if it ever does again.

If you use `compute_sgi`, `compute_dgi`, `evaluate`, `evaluate_batch`, `fit_thresholds`, `DGI`, `SGI`, `GroundingSwitch` or `set_default_encoder`, install the extra. The imports themselves are unchanged.

## What to change in your code

| If you had | Change it to |
|---|---|
| `from groundlens import check` used as `check(score)` | `from groundlens.geometry.render import render_check` |
| `pip install groundlens` and you use SGI or DGI | `pip install "groundlens[geometry]"` |
| a Python rule set from `groundlens.rules` | a YAML pack, then `check(..., ruleset=...)`. See [the shipped packs](https://github.com/groundlens-dev/groundlens/tree/main/packs) |
| a threshold on a score to decide escalation | `result.decision`, which is already the decision |

The legacy Python rule sets still exist in `groundlens.rules`. The two shipped packs, `eu-retail-banking` and `decision-rationale`, are ports of them, and each pack file records what changed in the port and why. Weights are gone from both, because 2.0 produces a decision and there is nothing for a weight to weigh.

## Version numbering

2.0.0 is SemVer and replaces the CalVer scheme. The rename of `check` is the breaking change that earns the major bump.

## What did not change

- `groundlens.audit.open_log` and its hash chain.
- The SGI and DGI formulas, thresholds and calibration behaviour.
- The licence. Apache-2.0, in `LICENSE`, in `pyproject.toml` and on the badge.
