# Domain Calibration Guide

This step-by-step guide walks through the complete process of calibrating DGI for a specific domain, evaluating the improvement, and deploying the calibration to production.

## Overview

Domain calibration replaces the generic reference direction $\hat{\boldsymbol{\mu}}$ with one computed from verified (question, response) pairs from your specific domain. This typically improves AUROC from ~0.76 to 0.90--0.99.

## Step 1: Collect Calibration Pairs

You need 20--100 verified (question, response) pairs where the response is known to be factually correct and grounded. Quality matters more than quantity.

!!! tip "Starting from zero pairs"
    If you don't have a labelled set yet, use [`DGI.propose_labels`](active-learning.md) to bootstrap one. It generates candidate pairs under five confabulation strategies, scores them with the current DGI `mu_hat`, and ranks the most uncertain for a human reviewer — exactly the pairs that will sharpen `mu_hat` the most when added to the calibration set.

### Sources of Calibration Pairs

| Source | Pros | Cons |
|---|---|---|
| Existing QA datasets | Pre-verified, diverse | May not match your domain exactly |
| Human-verified LLM outputs | Domain-matched | Requires expert review effort |
| Documentation FAQs | High quality, authoritative | Limited to documented topics |
| Support ticket resolutions | Real-world domain coverage | May need cleaning |

### Prepare the CSV

```csv
question,response
"What is the recommended dosage for metformin?","The initial dose is 500mg twice daily or 850mg once daily, titrated up to 2000mg/day."
"What are the contraindications for ACE inhibitors?","ACE inhibitors are contraindicated in bilateral renal artery stenosis, pregnancy, and history of angioedema."
"How should warfarin therapy be monitored?","INR should be monitored at least weekly during initiation and monthly once stable."
```

!!! tip "Pair quality checklist"
    - [ ] Each response is factually correct (verified by a domain expert)
    - [ ] Questions are representative of real usage in your domain
    - [ ] Responses are in the style your LLM produces (not copy-pasted from textbooks unless that is your use case)
    - [ ] No duplicate or near-duplicate pairs
    - [ ] At least 20 pairs (50+ recommended)

## Step 2: Run Calibration

=== "Python API"

    ```python
    from groundlens import calibrate

    result = calibrate(
        csv_path="medical_pairs.csv",
        metadata={
            "domain": "clinical-pharmacy",
            "source": "verified-qa-dataset-v2",
            "date": "2026-04-22",
        },
    )

    print(f"Pairs:         {result.n_pairs}")
    print(f"Embedding dim: {result.embedding_dim}")
    print(f"Concentration: {result.concentration:.2f}")
    ```

=== "CLI"

    ```bash
    groundlens calibrate \
        --pairs medical_pairs.csv \
        --output calibration_medical.json
    ```

### Evaluate the Concentration Parameter

The concentration $\kappa$ tells you how consistent your calibration data is:

| $\kappa$ | Quality | Action |
|---|---|---|
| > 10 | Excellent | Proceed to evaluation |
| 5--10 | Good | Proceed, but consider adding more pairs |
| 1--5 | Weak | Review pairs for noise or mixed domains |
| < 1 | Poor | Calibration data is too diverse; split into sub-domains |

## Step 3: Evaluate Improvement

Compare generic vs. calibrated DGI on a held-out test set.

```python
from groundlens import compute_dgi
from sklearn.metrics import roc_auc_score

# Load test data: list of (question, response, is_grounded) triples
test_data = load_test_set("medical_test.csv")

# Score with generic calibration
generic_scores = []
for q, r, label in test_data:
    result = compute_dgi(question=q, response=r)
    generic_scores.append((result.value, label))

# Score with domain calibration
calibrated_scores = []
for q, r, label in test_data:
    result = compute_dgi(
        question=q,
        response=r,
        reference_csv="medical_pairs.csv",
    )
    calibrated_scores.append((result.value, label))

# Compare AUROC
generic_auroc = roc_auc_score(
    [s[1] for s in generic_scores],
    [s[0] for s in generic_scores],
)
calibrated_auroc = roc_auc_score(
    [s[1] for s in calibrated_scores],
    [s[0] for s in calibrated_scores],
)

print(f"Generic AUROC:    {generic_auroc:.4f}")
print(f"Calibrated AUROC: {calibrated_auroc:.4f}")
print(f"Improvement:      +{calibrated_auroc - generic_auroc:.4f}")
```

!!! warning "Use a separate test set"
    Never evaluate on the same data you used for calibration. The calibration pairs define the reference direction; evaluating on them would be circular.

## Step 4: Save for Production

```python
# Save the calibration result
result.save("calibration_medical.json")

# Verify it loads correctly
from groundlens.calibrate import CalibrationResult
loaded = CalibrationResult.load("calibration_medical.json")
print(f"Loaded: {loaded.n_pairs} pairs, kappa={loaded.concentration:.2f}")
```

## Step 5: Deploy

Use the calibration CSV in production scoring:

```python
from groundlens import evaluate

score = evaluate(
    question=user_question,
    response=llm_response,
    reference_csv="medical_pairs.csv",
)
```

Or with the class API:

```python
from groundlens import DGI

# Initialize once at startup
dgi = DGI(reference_csv="medical_pairs.csv")

# Score each response
result = dgi.score(question=q, response=r)
```

## Recalibration Schedule

Recalibrate when:

- **Domain shifts**: Your domain evolves (new regulations, new terminology)
- **Model changes**: You switch to a different sentence-transformer model
- **Performance degradation**: Monitoring shows declining discrimination
- **Quarterly**: As a general best practice, recalibrate every 3 months

## Multi-Domain Calibration

For systems that serve multiple domains, maintain separate calibration files:

```python
from groundlens import DGI

# Initialize domain-specific scorers
dgi_medical = DGI(reference_csv="calibration_medical.csv")
dgi_legal = DGI(reference_csv="calibration_legal.csv")
dgi_finance = DGI(reference_csv="calibration_finance.csv")

# Route based on domain detection
def score_by_domain(question, response, domain):
    scorers = {
        "medical": dgi_medical,
        "legal": dgi_legal,
        "finance": dgi_finance,
    }
    scorer = scorers.get(domain, DGI())  # fall back to generic
    return scorer.score(question=question, response=response)
```

## Troubleshooting

### Low $\kappa$ after calibration

**Cause**: Calibration pairs span multiple topics or have inconsistent quality.

**Fix**: Filter pairs to a narrower domain, remove outliers, or split into sub-domains.

### No AUROC improvement

**Cause**: The test set may not match the calibration domain, or the generic direction already captures the relevant pattern.

**Fix**: Verify the test set is from the same domain as the calibration data. Check that test set labels are accurate.

### DGI scores cluster near zero

**Cause**: The displacement vectors are nearly orthogonal to the reference direction.

**Fix**: This usually indicates a calibration/scoring domain mismatch. Verify you are using the correct calibration file.
