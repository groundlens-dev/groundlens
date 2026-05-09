# CLI Reference

groundlens provides a command-line interface for quick checks, batch evaluation, calibration, and benchmarking. All commands are available via the `groundlens` entry point.

```bash
groundlens --help
groundlens --version
```

## `groundlens check`

Evaluate a single response for hallucination risk.

```bash
# With context (uses SGI)
groundlens check \
    --question "What is the capital of France?" \
    --response "The capital of France is Paris." \
    --context "France is in Western Europe. Its capital is Paris."

# Without context (uses DGI)
groundlens check \
    --question "What causes seasons on Earth?" \
    --response "Seasons are caused by Earth's 23.5-degree axial tilt."
```

**Output:**

```text
Method:      sgi
Score:       1.2341
Normalized:  0.6142
Flagged:     False
Explanation: SGI=1.234 -- strong context engagement (pass)
```

**Options:**

| Flag | Required | Default | Description |
|---|---|---|---|
| `--question` | Yes | --- | The input question |
| `--response` | Yes | --- | The LLM response to evaluate |
| `--context` | No | None | Source context (enables SGI when provided) |
| `--model` | No | `all-MiniLM-L6-v2` | Sentence-transformer model |

## `groundlens evaluate`

Batch evaluate a CSV file of question/response pairs.

```bash
groundlens evaluate input.csv --output results.csv
```

**Input CSV format:**

```csv
question,response,context
"What is X?","X is Y.","According to the manual, X is Y."
"What causes rain?","Rain is caused by condensation.",
```

The `context` column is optional. When present, SGI is used; when absent or empty, DGI is used.

**Output CSV** includes all original columns plus:

| Column | Description |
|---|---|
| `groundlens_method` | `sgi` or `dgi` |
| `groundlens_score` | Raw score value |
| `groundlens_normalized` | Score in [0, 1] |
| `groundlens_flagged` | `True` or `False` |
| `groundlens_explanation` | Human-readable interpretation |

**Options:**

| Flag | Required | Default | Description |
|---|---|---|---|
| `input_csv` | Yes (positional) | --- | Input CSV file path |
| `--output` | Yes | --- | Output CSV file path |
| `--model` | No | `all-MiniLM-L6-v2` | Sentence-transformer model |
| `--reference-csv` | No | None | DGI calibration CSV path |

!!! tip "CI/CD integration"
    Use `groundlens evaluate` in your CI pipeline to gate deployments on hallucination scores. Parse the output CSV and fail the build if any row has `groundlens_flagged=True`.

## `groundlens calibrate`

Compute a DGI reference direction from domain-specific calibration pairs.

```bash
groundlens calibrate \
    --pairs domain_pairs.csv \
    --output calibration.json
```

**Input CSV format:**

```csv
question,response
"What is the dosage for ibuprofen?","The recommended dosage is 200-400mg every 4-6 hours."
"What are the side effects of aspirin?","Common side effects include stomach irritation and bleeding risk."
```

The CSV must contain verified grounded (question, response) pairs from your target domain. A minimum of 5 pairs is required; 20--100 pairs is recommended for reliable calibration.

**Output:**

```text
Calibration complete.
  Pairs:         47
  Embedding dim: 384
  Concentration: 12.34
  Saved to:      calibration.json
```

The saved JSON contains the reference direction vector (`mu_hat`), the concentration parameter ($\kappa$), and metadata. Use it with:

```bash
groundlens evaluate input.csv --output results.csv --reference-csv domain_pairs.csv
```

**Options:**

| Flag | Required | Default | Description |
|---|---|---|---|
| `--pairs` | Yes | --- | CSV with question,response columns |
| `--output` | Yes | --- | Output JSON file path |
| `--model` | No | `all-MiniLM-L6-v2` | Sentence-transformer model |

## `groundlens benchmark`

Run the confabulation benchmark against a HuggingFace dataset.

```bash
groundlens benchmark
groundlens benchmark --dataset cert-framework/human-confabulation-benchmark
```

**Output:**

```text
Loading dataset: cert-framework/human-confabulation-benchmark
Running benchmark on 200 items...
  Processed 200/200

--- Benchmark Results ---
SGI AUROC: 0.8234 (n=150)
DGI AUROC: 0.9580 (n=200)
```

!!! note "Dependencies"
    The benchmark command requires `datasets` (HuggingFace) and `scikit-learn` for AUROC computation. Install with:
    ```bash
    pip install datasets scikit-learn
    ```

**Options:**

| Flag | Required | Default | Description |
|---|---|---|---|
| `--dataset` | No | `cert-framework/human-confabulation-benchmark` | HuggingFace dataset name |
| `--model` | No | `all-MiniLM-L6-v2` | Sentence-transformer model |
