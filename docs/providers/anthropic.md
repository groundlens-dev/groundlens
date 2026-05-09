# Anthropic Provider

`GroundlensAnthropic` wraps the Anthropic Python SDK and automatically scores every Claude response for hallucination risk using groundlens.

## Installation

```bash
pip install "groundlens[anthropic]"
```

## Quick Start

```python
from groundlens.providers.anthropic import GroundlensAnthropic

llm = GroundlensAnthropic(api_key="sk-ant-...")

# With context (SGI scoring)
resp = llm.chat(
    "Summarize the key findings.",
    context="The study found that regular exercise reduces cardiovascular risk by 30%...",
)
print(resp.text)
print(resp.groundlens_score.method)         # 'sgi'
print(resp.groundlens_score.flagged)        # False

# Without context (DGI scoring)
resp = llm.chat("What is the Pythagorean theorem?")
print(resp.groundlens_score.method)         # 'dgi'
```

## Configuration

```python
llm = GroundlensAnthropic(
    api_key="sk-ant-...",
    model="claude-sonnet-4-20250514",      # Claude model for generation
    groundlens_model="all-MiniLM-L6-v2",    # Sentence-transformer for scoring
    groundlens_threshold=0.45,               # Reserved for future use
)
```

| Parameter | Default | Description |
|---|---|---|
| `api_key` | Required | Anthropic API key |
| `model` | `"claude-sonnet-4-20250514"` | Claude model for generation |
| `groundlens_model` | `"all-MiniLM-L6-v2"` | Embedding model for scoring |
| `groundlens_threshold` | `0.45` | Reserved for future threshold customization |

## Response Object

The `LLMResponse` returned by `chat()` contains:

| Field | Type | Description |
|---|---|---|
| `text` | `str` | Generated response text |
| `model` | `str` | Model identifier |
| `usage` | `dict` | Token usage (`input_tokens`, `output_tokens`) |
| `groundlens_score` | `GroundlensScore` | Full groundlens evaluation result |

## Passing Extra Parameters

Additional keyword arguments are forwarded to `messages.create`:

```python
resp = llm.chat(
    "Explain the theory of relativity.",
    max_tokens=1000,
)
```

The `max_tokens` parameter defaults to 4096 if not specified.

## Convenience Method

```python
# complete() delegates to chat()
resp = llm.complete("Summarize this document.", context=document_text)
```

## Environment Variable for API Key

```python
import os
from groundlens.providers.anthropic import GroundlensAnthropic

llm = GroundlensAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
```
