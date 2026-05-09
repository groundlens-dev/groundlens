# OpenAI Provider

`GroundlensOpenAI` wraps the OpenAI Python SDK and automatically scores every response for hallucination risk using groundlens.

## Installation

```bash
pip install "groundlens[openai]"
```

## Quick Start

```python
from groundlens.providers.openai import GroundlensOpenAI

llm = GroundlensOpenAI(api_key="sk-...")

# With context (SGI scoring)
resp = llm.chat(
    "Summarize this document.",
    context="The document discusses the effects of climate change on coral reefs...",
)
print(resp.text)                          # The LLM's response
print(resp.groundlens_score.method)         # 'sgi'
print(resp.groundlens_score.value)          # e.g., 1.23
print(resp.groundlens_score.flagged)        # False
print(resp.groundlens_score.explanation)    # Human-readable

# Without context (DGI scoring)
resp = llm.chat("What causes seasons on Earth?")
print(resp.groundlens_score.method)         # 'dgi'
```

## Configuration

```python
llm = GroundlensOpenAI(
    api_key="sk-...",
    model="gpt-4o",                     # OpenAI model for generation
    groundlens_model="all-MiniLM-L6-v2",  # Sentence-transformer for scoring
    groundlens_threshold=0.45,             # Reserved for future use
)
```

| Parameter | Default | Description |
|---|---|---|
| `api_key` | Required | OpenAI API key |
| `model` | `"gpt-4o"` | Chat model for generation |
| `groundlens_model` | `"all-MiniLM-L6-v2"` | Embedding model for scoring |
| `groundlens_threshold` | `0.45` | Reserved for future threshold customization |

## Response Object

The `LLMResponse` returned by `chat()` contains:

| Field | Type | Description |
|---|---|---|
| `text` | `str` | Generated response text |
| `model` | `str` | Model identifier |
| `usage` | `dict` | Token usage (`prompt_tokens`, `completion_tokens`, `total_tokens`) |
| `groundlens_score` | `GroundlensScore` | Full groundlens evaluation result |

## Passing Extra Parameters

Additional keyword arguments are forwarded to `chat.completions.create`:

```python
resp = llm.chat(
    "Explain quantum entanglement.",
    temperature=0.2,
    max_tokens=500,
)
```

## Decision Patterns

```python
resp = llm.chat("What is the recommended treatment?", context=medical_context)

if resp.groundlens_score.flagged:
    # Response may not be grounded in the provided context
    fallback_response = "I cannot verify this answer against the provided sources."
else:
    # Response appears grounded
    final_response = resp.text
```

## Environment Variable for API Key

```python
import os
from groundlens.providers.openai import GroundlensOpenAI

llm = GroundlensOpenAI(api_key=os.environ["OPENAI_API_KEY"])
```
