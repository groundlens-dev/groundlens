# Google Gemini Provider

`GroundlensGemini` wraps the Google Generative AI Python SDK and automatically scores every Gemini response for hallucination risk using groundlens.

## Installation

```bash
pip install "groundlens[google]"
```

This installs the `google-generativeai` package.

## Quick Start

```python
from groundlens.providers.google import GroundlensGemini

llm = GroundlensGemini(api_key="AI...")

# With context (SGI scoring)
resp = llm.chat(
    "What are the main conclusions?",
    context="The report concludes that renewable energy costs have decreased by 70% since 2010...",
)
print(resp.text)
print(resp.groundlens_score.method)         # 'sgi'
print(resp.groundlens_score.flagged)        # False

# Without context (DGI scoring)
resp = llm.chat("How does DNA replication work?")
print(resp.groundlens_score.method)         # 'dgi'
```

## Configuration

```python
llm = GroundlensGemini(
    api_key="AI...",
    model="gemini-2.0-flash",             # Gemini model for generation
    groundlens_model="all-MiniLM-L6-v2",    # Sentence-transformer for scoring
    groundlens_threshold=0.45,               # Reserved for future use
)
```

| Parameter | Default | Description |
|---|---|---|
| `api_key` | Required | Google AI API key |
| `model` | `"gemini-2.0-flash"` | Gemini model for generation |
| `groundlens_model` | `"all-MiniLM-L6-v2"` | Embedding model for scoring |
| `groundlens_threshold` | `0.45` | Reserved for future threshold customization |

## Response Object

The `LLMResponse` returned by `chat()` contains:

| Field | Type | Description |
|---|---|---|
| `text` | `str` | Generated response text |
| `model` | `str` | Model identifier |
| `usage` | `dict` | Token usage (when available from the API) |
| `groundlens_score` | `GroundlensScore` | Full groundlens evaluation result |

Usage metadata includes `prompt_token_count`, `candidates_token_count`, and `total_token_count` when provided by the Gemini API.

## Passing Extra Parameters

Additional keyword arguments are forwarded to `generate_content`:

```python
resp = llm.chat(
    "Summarize the research paper.",
    context=paper_abstract,
    generation_config={"temperature": 0.3},
)
```

## Convenience Method

```python
resp = llm.complete("Explain the water cycle.", context=source_text)
```

## Environment Variable for API Key

```python
import os
from groundlens.providers.google import GroundlensGemini

llm = GroundlensGemini(api_key=os.environ["GOOGLE_API_KEY"])
```
