# Calibration

GroundLens ships no threshold. A threshold fitted on someone else's data does
not transfer, because the grounded floor moves with answer length, style and
domain. `calibrate()` is how you get a threshold from **your** traffic, and it
always hands you the bill along with it.

## The idea

You label a sample of your own answers as defect or not, and `calibrate()`
returns the threshold that catches your target share of defects — plus the
false-positive rate you pay for it, with a bootstrap confidence interval. You
cannot get the cut without seeing the cost.

```{code-block} python
from groundlens import calibrate

labelled = [
    (proofread_result_or_float, is_defect),   # from your own traffic
    # ...
]
op = calibrate(labelled, target_recall=0.95)

print("threshold:", op.threshold)
print("false-positive rate:", op.fpr)         # read this first
```

`op` is an {class}`groundlens.OperatingPoint` carrying `threshold` **and** `fpr`
with a 95% interval. See {func}`groundlens.calibrate` for every argument.

## Why the false-positive rate comes first

Many grounding methods, told to catch 95% of hallucinations, flag almost
everything — some sit at a false-positive rate of 1.00, worse than random. A
threshold quoted without its false-positive rate hides that. `calibrate()`
refuses to: `fpr` is returned next to `threshold`, so you see what a given recall
actually costs on your data before you deploy it.

## How much to label

Below a minimum number of labelled examples the interval is wide and the
estimate is rough; `calibrate()` says so. Lower `min_labelled` only while you are
exploring, never to deploy. The `seed` is fixed by default so the bootstrap
interval is reproducible.

## Putting the threshold into a policy

Take the `threshold` and set it as the verifier's `support_min` in your policy,
with a guard band at least twice the verifier's tolerance:

```{code-block} yaml
thresholds:
  groundlens.lexical: { support_min: 0.61, guard_band: 0.02 }
```

See [Writing a policy](writing-policies.md).
