# Semantic Kernel Integration

`GroundlensFilter` is a function invocation filter for Microsoft Semantic Kernel that automatically evaluates function results for hallucination risk.

## Installation

```bash
pip install "groundlens[semantic-kernel]"
```

## Quick Start

```python
from groundlens.integrations.semantic_kernel import GroundlensFilter

filt = GroundlensFilter()

# Register with Semantic Kernel
kernel.add_filter("function_invocation", filt)
```

## Configuration

```python
filt = GroundlensFilter(
    groundlens_model="all-MiniLM-L6-v2",  # Embedding model
    input_key="input",                    # Key for question in function args
    context_key="context",                # Key for context in function args
)
```

| Parameter | Default | Description |
|---|---|---|
| `groundlens_model` | `"all-MiniLM-L6-v2"` | Sentence-transformer for scoring |
| `input_key` | `"input"` | Key to extract question from function arguments |
| `context_key` | `"context"` | Key to extract context from function arguments |

## How It Works

The filter operates as an async function invocation interceptor:

1. The filter calls `await next(context)` to execute the actual function.
2. It extracts the question from `context.arguments[input_key]`.
3. It extracts the result from `context.result.value`.
4. It optionally extracts context from `context.arguments[context_key]`.
5. It evaluates the result with groundlens (SGI if context is present, DGI otherwise).
6. It attaches the score to `context.metadata["groundlens_score"]`.
7. It stores the score in `filt.scores` for later inspection.

## Accessing Scores

```python
filt = GroundlensFilter()
kernel.add_filter("function_invocation", filt)

# ... run functions ...

# Inspect scores after execution
for function_name, score in filt.scores:
    status = "FLAGGED" if score.flagged else "PASS"
    print(f"{function_name}: {score.method} = {score.value:.3f} ({status})")
```

## Complete Example

```python
import semantic_kernel as sk
from semantic_kernel.functions import kernel_function
from groundlens.integrations.semantic_kernel import GroundlensFilter

# Create kernel and register filter
kernel = sk.Kernel()
filt = GroundlensFilter()
kernel.add_filter("function_invocation", filt)

# Define a semantic function
class QAPlugin:
    @kernel_function(name="answer_question")
    async def answer(self, input: str, context: str = "") -> str:
        # This would normally call an LLM
        return "The answer based on the provided context..."

kernel.add_plugin(QAPlugin(), "qa")

# Invoke -- the filter automatically scores the result
result = await kernel.invoke(
    "qa",
    "answer_question",
    input="What is the treatment for condition X?",
    context="Treatment guidelines state...",
)

# Check the groundlens score
for fn_name, score in filt.scores:
    print(f"{fn_name}: {score.explanation}")
```

## Logging

The filter logs at two levels:

- **WARNING**: When a function result is flagged for hallucination risk
- **INFO**: When a function result passes verification

```python
import logging
logging.basicConfig(level=logging.INFO)
# GroundlensFilter events now appear in logs
```
