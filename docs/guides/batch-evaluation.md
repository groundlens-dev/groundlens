# Batch Evaluation

This guide covers using `evaluate_batch()` and the CLI `groundlens evaluate` command for scoring large sets of LLM outputs, suitable for CI/CD pipelines, regression testing, and quality monitoring.

## Python API: evaluate_batch()

```python
from groundlens import evaluate_batch

items = [
    {
        "question": "What is the capital of France?",
        "response": "The capital of France is Paris.",
        "context": "Paris is the capital of France.",
    },
    {
        "question": "What causes tides?",
        "response": "Tides are caused by gravitational forces from the Moon and Sun.",
    },
    {
        "question": "What is photosynthesis?",
        "response": "Photosynthesis is the process by which plants convert light into energy.",
        "context": "Plants use photosynthesis to convert sunlight, water, and CO2 into glucose and oxygen.",
    },
]

results = evaluate_batch(items)

for i, score in enumerate(results):
    status = "FLAGGED" if score.flagged else "PASS"
    print(f"[{i}] {score.method.upper()} = {score.value:.3f} ({status})")
```

### Input Format

Each item is a dict with:

| Key | Required | Description |
|---|---|---|
| `question` | Yes | The input question or prompt |
| `response` | Yes | The LLM-generated response |
| `context` | No | Source context (triggers SGI when present) |

### Options

```python
results = evaluate_batch(
    items,
    model="all-MiniLM-L6-v2",          # Sentence-transformer model
    reference_csv="domain_pairs.csv",    # DGI calibration (for items without context)
)
```

## CLI: groundlens evaluate

For batch evaluation from the command line:

```bash
groundlens evaluate input.csv --output results.csv
```

### Input CSV

```csv
question,response,context
"What is X?","X is Y.","According to docs, X is Y."
"What causes Z?","Z happens because of W.",
```

### Output CSV

The output includes all original columns plus groundlens scores:

```csv
question,response,context,groundlens_method,groundlens_score,groundlens_normalized,groundlens_flagged,groundlens_explanation
"What is X?","X is Y.","According to docs, X is Y.",sgi,1.2341,0.6142,False,"SGI=1.234 -- strong context engagement (pass)"
"What causes Z?","Z happens because of W.",,dgi,0.4521,0.7261,False,"DGI=0.452 -- aligns with grounded patterns (pass)"
```

With domain calibration:

```bash
groundlens evaluate input.csv --output results.csv --reference-csv domain_pairs.csv
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Hallucination Gate
on: [push]

jobs:
  groundlens:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install groundlens
        run: pip install groundlens

      - name: Run evaluation
        run: |
          groundlens evaluate tests/golden_qa.csv --output results.csv

      - name: Check for flagged responses
        run: |
          flagged=$(grep -c "True" results.csv | head -1 || echo 0)
          if [ "$flagged" -gt "0" ]; then
            echo "FAIL: $flagged responses flagged for hallucination"
            exit 1
          fi
```

### Python CI Script

```python
import sys
from groundlens import evaluate_batch

# Load test cases
items = load_golden_dataset("tests/golden_qa.json")

results = evaluate_batch(items)

flagged = [r for r in results if r.flagged]

if flagged:
    print(f"FAIL: {len(flagged)}/{len(results)} responses flagged")
    for r in flagged:
        print(f"  - {r.method}: {r.value:.3f} -- {r.explanation}")
    sys.exit(1)

print(f"PASS: {len(results)} responses evaluated, 0 flagged")
```

## Aggregating Results

### Summary Statistics

```python
import statistics

results = evaluate_batch(items)

values = [r.value for r in results]
flagged_count = sum(1 for r in results if r.flagged)

print(f"Total:    {len(results)}")
print(f"Flagged:  {flagged_count} ({100 * flagged_count / len(results):.1f}%)")
print(f"Mean:     {statistics.mean(values):.3f}")
print(f"Median:   {statistics.median(values):.3f}")
print(f"Std dev:  {statistics.stdev(values):.3f}")
```

### By Method

```python
sgi_results = [r for r in results if r.method == "sgi"]
dgi_results = [r for r in results if r.method == "dgi"]

print(f"SGI: {len(sgi_results)} items, {sum(1 for r in sgi_results if r.flagged)} flagged")
print(f"DGI: {len(dgi_results)} items, {sum(1 for r in dgi_results if r.flagged)} flagged")
```

## Performance Considerations

| Dataset size | Approximate time | Notes |
|---|---|---|
| 10 items | ~1s | Includes model loading |
| 100 items | ~5s | Model cached after first item |
| 1,000 items | ~30s | Linear scaling |
| 10,000 items | ~5 min | Consider parallelization |

!!! tip "First-call overhead"
    The first call loads the sentence-transformer model (~1--2s). Subsequent items are fast (~5ms each for embedding + scoring).

For very large datasets, consider splitting into chunks and processing in parallel:

```python
from concurrent.futures import ProcessPoolExecutor
from groundlens import evaluate_batch


def evaluate_chunk(chunk):
    return evaluate_batch(chunk)


chunks = [items[i:i+500] for i in range(0, len(items), 500)]

with ProcessPoolExecutor(max_workers=4) as executor:
    chunk_results = list(executor.map(evaluate_chunk, chunks))

all_results = [r for chunk in chunk_results for r in chunk]
```
