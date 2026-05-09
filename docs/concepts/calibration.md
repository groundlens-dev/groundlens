# Calibration

DGI accuracy depends on the quality of the reference direction $\hat{\mu}$. **Domain-specific calibration** is the single most impactful step you can take to improve groundlens accuracy in production.

## Why Calibrate?

The bundled generic reference direction is trained on diverse question-answer pairs across many domains. It captures a "universal" grounded displacement direction that achieves AUROC ~0.76 --- useful for prototyping but insufficient for production.

Different domains have different displacement patterns:

- **Legal**: Questions about statutes produce responses with specific citation patterns
- **Medical**: Clinical questions produce responses with diagnostic terminology shifts
- **Financial**: Regulatory questions produce responses with compliance-specific elaboration

Domain-specific calibration captures these patterns, typically improving AUROC to 0.90--0.99.

| Domain | Generic AUROC | Calibrated AUROC | Improvement |
|---|---|---|---|
| Generic | 0.76 | --- | Baseline |
| Legal | 0.76 | 0.94 | +0.18 |
| Medical | 0.76 | 0.97 | +0.21 |
| Financial | 0.76 | 0.92 | +0.16 |
| Technical docs | 0.76 | 0.95 | +0.19 |

## How to Collect Calibration Pairs

You need 20--100 verified (question, response) pairs where the response is known to be factually grounded. Sources:

1. **Existing QA datasets**: If you have a validated QA dataset for your domain, use it directly.
2. **Human-verified LLM outputs**: Run your LLM on representative questions and have a subject-matter expert verify the answers.
3. **Documentation extraction**: Extract question-answer pairs from official documentation, FAQs, or knowledge bases.

!!! tip "Quality over quantity"
    20 high-quality pairs outperform 200 noisy pairs. Each pair should represent a genuine question and a verified correct response from your target domain.

### CSV Format

```csv
question,response
"What is the recommended dosage for ibuprofen?","The recommended dosage is 200-400mg every 4-6 hours for adults."
"What are the contraindications for aspirin?","Aspirin is contraindicated in patients with aspirin allergy, active bleeding, or hemophilia."
```

## The calibrate() API

```python
from groundlens import calibrate

# From a CSV file
result = calibrate(csv_path="my_domain_pairs.csv")

# From pairs directly
result = calibrate(
    pairs=[
        ("What is the dosage for X?", "The recommended dosage is Y."),
        ("What are the side effects?", "Common side effects include Z."),
        # ... at least 5 pairs, ideally 20-100
    ],
    metadata={"domain": "pharmacy", "date": "2026-04-22"},
)

print(f"Pairs:         {result.n_pairs}")
print(f"Embedding dim: {result.embedding_dim}")
print(f"Concentration: {result.concentration:.2f}")
```

## Understanding the Result

The `CalibrationResult` contains:

| Field | Type | Description |
|---|---|---|
| `model` | `str` | Sentence-transformer model used |
| `n_pairs` | `int` | Number of calibration pairs |
| `embedding_dim` | `int` | Dimensionality of the embedding space |
| `mu_hat` | `ndarray` | The computed reference direction vector |
| `concentration` | `float` | Estimated $\kappa$ parameter of the von Mises-Fisher distribution |
| `metadata` | `dict` | User-attached metadata |

### The Concentration Parameter ($\kappa$)

The concentration parameter indicates how consistent the displacement directions are in your calibration data:

- **$\kappa$ > 10**: Highly consistent --- your domain has a strong, clear grounded direction. Expect good discrimination.
- **$\kappa$ 5--10**: Moderately consistent --- reasonable calibration quality.
- **$\kappa$ < 5**: Low consistency --- the calibration pairs may be too diverse, noisy, or from mixed domains. Consider filtering.

## Saving and Loading

```python
# Save calibration for production use
result.save("calibration_pharmacy.json")

# Load in production
from groundlens.calibrate import CalibrationResult
loaded = CalibrationResult.load("calibration_pharmacy.json")
print(loaded.concentration)
```

The saved JSON contains all fields needed to reconstruct the reference direction without recomputing from pairs.

## Using Calibration in Production

=== "Function API"

    ```python
    from groundlens import compute_dgi

    result = compute_dgi(
        question="What is the dosage for X?",
        response="The recommended dosage is Y.",
        reference_csv="my_domain_pairs.csv",
    )
    ```

=== "Class API"

    ```python
    from groundlens import DGI

    dgi = DGI(reference_csv="my_domain_pairs.csv")
    result = dgi.score(question="...", response="...")
    ```

=== "evaluate() API"

    ```python
    from groundlens import evaluate

    score = evaluate(
        question="...",
        response="...",
        reference_csv="my_domain_pairs.csv",
    )
    ```

!!! warning "Model consistency"
    The calibration must use the same embedding model as the scoring. If you calibrate with `all-MiniLM-L6-v2`, you must score with `all-MiniLM-L6-v2`. Mixing models produces undefined behavior because the embedding spaces are geometrically different.

## Next Steps

- [Domain Calibration Guide](../guides/domain-calibration.md) --- step-by-step walkthrough with evaluation
- [DGI Mathematics](../theory/dgi-mathematics.md) --- the von Mises-Fisher theory behind calibration
