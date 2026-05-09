# AutoGen Integration

`GroundlensChecker` evaluates agent replies in AutoGen conversations for hallucination risk, providing a structured verification result.

## Installation

```bash
pip install "groundlens[autogen]"
```

This installs the `pyautogen` package.

## Quick Start

```python
from groundlens.integrations.autogen import GroundlensChecker

checker = GroundlensChecker()

messages = [
    {"role": "user", "content": "What is the capital of France?"},
    {"role": "assistant", "content": "The capital of France is Paris."},
]

result = checker.check(messages, sender=None)
print(result)
```

**Output:**

```python
{
    "score": 0.452,
    "normalized": 0.726,
    "flagged": False,
    "method": "dgi",
    "explanation": "DGI=0.452 -- aligns with grounded patterns (pass)",
}
```

## Configuration

```python
checker = GroundlensChecker(
    groundlens_model="all-MiniLM-L6-v2",  # Embedding model
    context_key="context",                # Metadata key for context
)
```

| Parameter | Default | Description |
|---|---|---|
| `groundlens_model` | `"all-MiniLM-L6-v2"` | Sentence-transformer for scoring |
| `context_key` | `"context"` | Key to look for context in message metadata |

## How It Works

The checker processes conversation messages:

1. Extracts the **last message** as the response (the assistant's reply).
2. Searches backward through the conversation for the most recent **user message** as the question.
3. Looks for context in three places:
    - `kwargs["context"]` (passed directly)
    - Message `metadata` dicts (any message with a `context` metadata key)
4. Evaluates with SGI (if context found) or DGI (if no context).
5. Returns a structured dict with the result.

## Result Format

The returned dict contains:

| Key | Type | Description |
|---|---|---|
| `score` | `float` | Raw groundlens score |
| `normalized` | `float` | Score in [0, 1] |
| `flagged` | `bool` | Whether human review is recommended |
| `method` | `str` | `"sgi"` or `"dgi"` |
| `explanation` | `str` | Human-readable interpretation |

## Providing Context

### Via kwargs

```python
result = checker.check(
    messages=messages,
    sender=agent,
    context="The reference document states that Paris is the capital of France.",
)
# Uses SGI scoring
```

### Via Message Metadata

```python
messages = [
    {
        "role": "user",
        "content": "What is the capital of France?",
        "metadata": {"context": "Paris is the capital of France."},
    },
    {"role": "assistant", "content": "The capital of France is Paris."},
]

result = checker.check(messages, sender=None)
# Detects context from metadata, uses SGI scoring
```

## Using with AutoGen Agents

```python
import autogen
from groundlens.integrations.autogen import GroundlensChecker

checker = GroundlensChecker()

# Create agents
assistant = autogen.AssistantAgent(
    name="assistant",
    llm_config={"model": "gpt-4o"},
)

user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
)

# After conversation, verify the last reply
def verify_reply(messages, sender):
    result = checker.check(messages, sender)
    if result["flagged"]:
        print(f"WARNING: Response flagged -- {result['explanation']}")
    return result

# Register as a reply function
user_proxy.register_reply(
    [autogen.AssistantAgent],
    lambda recipient, messages, sender, config: verify_reply(messages, sender),
)
```

## Logging

The checker logs at two levels:

- **WARNING**: When a response is flagged (includes explanation)
- **INFO**: When a response passes verification

```python
import logging
logging.basicConfig(level=logging.INFO)
```
