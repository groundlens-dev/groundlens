---
title: groundlens API
emoji: 📐
colorFrom: yellow
colorTo: red
sdk: docker
pinned: false
license: mit
tags:
- hallucination-detection
- llm-evaluation
- rag
- grounding
- groundlens
- api
short_description: REST API for geometric LLM hallucination detection
---

# groundlens API

REST API for [groundlens](https://groundlens.dev) — LLM hallucination detection using embedding geometry.

No second LLM. Deterministic. Same inputs → same scores.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/check` | Auto-selects SGI or DGI based on context |
| `POST` | `/v1/sgi` | Context-based grounding check |
| `POST` | `/v1/dgi` | Context-free grounding check |
| `GET` | `/health` | Liveness + model status |
| `GET` | `/docs` | Interactive Swagger UI |

## Quick start

### Check without context (DGI)

```bash
curl -X POST https://groundlens-groundlens-api.hf.space/v1/check \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the capital of France?",
    "response": "The capital of France is Paris."
  }'
```

### Check with context (SGI)

```bash
curl -X POST https://groundlens-groundlens-api.hf.space/v1/check \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What does our policy cover?",
    "response": "The policy covers fire, flood, and theft damage to residential properties.",
    "context": "HomeShield Insurance Policy: Coverage includes damage from fire, flood, and theft for residential properties within the continental United States."
  }'
```

### Python

```python
import requests

r = requests.post(
    "https://groundlens-groundlens-api.hf.space/v1/check",
    json={
        "question": "What is the capital of France?",
        "response": "The capital of France is Paris.",
    },
)
print(r.json()["verdict"])  # GROUNDED
```

### JavaScript

```javascript
const res = await fetch("https://groundlens-groundlens-api.hf.space/v1/check", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    question: "What is the capital of France?",
    response: "The capital of France is Paris.",
  }),
});
const data = await res.json();
console.log(data.verdict); // GROUNDED
```

## Response format

```json
{
  "verdict": "GROUNDED",
  "flagged": false,
  "method": "DGI (Directional Grounding Index)",
  "score": 0.4521,
  "threshold": 0.30,
  "explanation": "The response follows patterns typical of grounded answers.",
  "detail": {
    "interpretation": "Positive directional alignment with grounded response patterns."
  },
  "latency_ms": 45
}
```

## Self-hosting

```bash
git clone https://github.com/groundlens-dev/groundlens-api.git
cd groundlens-api
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Or with Docker:

```bash
docker build -t groundlens-api .
docker run -p 8000:7860 groundlens-api
```

## Links

- [groundlens library](https://github.com/groundlens-dev/groundlens) — `pip install groundlens`
- [MCP Server](https://github.com/groundlens-dev/groundlens-mcp) — for Claude Desktop, Cursor, Windsurf
- [Demo](https://huggingface.co/spaces/groundlens/groundlens-demo) — interactive web UI
- [Documentation](https://docs.groundlens.dev)
- [Website](https://groundlens.dev)
