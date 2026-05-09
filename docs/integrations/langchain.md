# LangChain Integration

groundlens provides two LangChain integration components: `GroundlensEvaluator` for LangSmith experiment evaluation, and `GroundlensCallback` for real-time chain monitoring.

## Installation

```bash
pip install "groundlens[langchain]"
```

This installs `langsmith` and `langchain-core`.

## GroundlensEvaluator

The evaluator implements the LangSmith `RunEvaluator` protocol, enabling groundlens as an evaluator in LangSmith experiment pipelines.

### Basic Usage

```python
from groundlens.integrations.langchain import GroundlensEvaluator
from langsmith import evaluate as ls_evaluate

evaluator = GroundlensEvaluator()

# Run evaluation against a LangSmith dataset
results = ls_evaluate(
    my_chain,
    data="my-qa-dataset",
    evaluators=[evaluator],
)
```

### Configuration

```python
evaluator = GroundlensEvaluator(
    groundlens_model="all-MiniLM-L6-v2",  # Embedding model
    input_key="question",                 # Key for question in run inputs
    output_key="output",                  # Key for response in run outputs
    context_key="context",                # Key for context in example inputs
)
```

| Parameter | Default | Description |
|---|---|---|
| `groundlens_model` | `"all-MiniLM-L6-v2"` | Sentence-transformer for scoring |
| `input_key` | `"question"` | Key to extract question from run inputs |
| `output_key` | `"output"` | Key to extract response from run outputs |
| `context_key` | `"context"` | Key to extract context from example inputs |

### Key Extraction

The evaluator attempts to find the question from run inputs using the `input_key`. If not found, it falls back to checking `"input"`, `"query"`, and `"prompt"` keys. Similarly, for the response, it checks `output_key` first, then `"answer"`, `"result"`, `"text"`, and `"response"`.

Context is extracted from the `example.inputs` dict (the ground-truth/reference data in LangSmith). When context is present, SGI scoring is used; when absent, DGI scoring is applied.

### Result Format

The evaluator returns a LangSmith `EvaluationResult` with:

- `key`: `"groundlens"`
- `score`: The normalized groundlens score (0--1)
- `comment`: The human-readable explanation

## GroundlensCallback

The callback handler intercepts every LLM call in a LangChain chain and scores the response in real time. Flagged responses generate log warnings.

### Basic Usage

```python
from groundlens.integrations.langchain import GroundlensCallback
from langchain_openai import ChatOpenAI

cb = GroundlensCallback()
llm = ChatOpenAI(callbacks=[cb])

# Every LLM call is automatically scored
result = llm.invoke("What is the capital of France?")

# Inspect scores after execution
for run_id, score in cb.scores.items():
    print(f"{run_id}: {score.method} = {score.value:.3f} ({score.explanation})")
```

### Configuration

```python
cb = GroundlensCallback(
    groundlens_model="all-MiniLM-L6-v2",  # Embedding model
    context_key="context",                # Metadata key for context
)
```

### Providing Context

Pass context via the `metadata` parameter:

```python
result = llm.invoke(
    "Summarize this document.",
    metadata={"context": "The document discusses renewable energy trends..."},
)
```

When context is found in metadata, SGI scoring is used. Otherwise, DGI scoring is applied.

### Accessing Scores

All scores are stored in `cb.scores`, keyed by LangChain run UUID:

```python
cb = GroundlensCallback()
llm = ChatOpenAI(callbacks=[cb])

llm.invoke("Question 1?")
llm.invoke("Question 2?")

# Iterate all scores
for run_id, score in cb.scores.items():
    if score.flagged:
        print(f"WARNING: Run {run_id} flagged -- {score.explanation}")
```

### Logging

The callback uses Python's `logging` module:

- **WARNING** level for flagged responses
- **INFO** level for passing responses
- **DEBUG** level for lifecycle events (start, end, error)

```python
import logging
logging.basicConfig(level=logging.INFO)

# Now groundlens callback events appear in logs
cb = GroundlensCallback()
```

## Using Both Together

For comprehensive monitoring, use the callback for real-time alerting and the evaluator for batch experiment evaluation:

```python
from groundlens.integrations.langchain import GroundlensCallback, GroundlensEvaluator
from langchain_openai import ChatOpenAI
from langsmith import evaluate as ls_evaluate

# Real-time monitoring
cb = GroundlensCallback()
llm = ChatOpenAI(callbacks=[cb])

# Batch evaluation
evaluator = GroundlensEvaluator()
results = ls_evaluate(llm, data="dataset", evaluators=[evaluator])
```
