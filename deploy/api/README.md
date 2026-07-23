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
short_description: REST API for deterministic grounding checks (SGI/DGI)
---

# groundlens API

REST API for [groundlens](https://groundlens.dev) — a deterministic first-stage grounding check using embedding geometry. It checks whether a response was drawn from its source, not whether the source supports it.

No model in the scoring path. Deterministic. Same inputs → same scores. Every response carries `escalate` and `handoff`: a passing check means the answer came from the source, not that its facts are right.

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
print(r.json()["check"])     # e.g. "Looks grounded"
print(r.json()["handoff"])   # what geometry cannot settle
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
console.log(data.check);   // e.g. "Looks grounded"
console.log(data.handoff); // what geometry cannot settle
```

## Response format

```json
{
  "check": "Looks grounded",
  "level": "ok",
  "escalate": false,
  "handoff": "Grounding, not facts: a plausible wrong fact in the right frame would pass this check. Verify facts in a second stage.",
  "flagged": false,
  "method": "DGI (Directional Grounding Index)",
  "score": 0.4521,
  "threshold": 0.30,
  "explanation": "The answer moves the way well-grounded answers usually do.",
  "detail": {
    "interpretation": "Positive directional alignment with grounded response patterns."
  },
  "latency_ms": 45
}
```

**`check` is not a verdict, and `handoff` is not optional.** A pass means the response was drawn from its source. It does not mean the facts are right: an in-register factual substitution (right frame, wrong number) passes this check by design. Render the handoff, and route `escalate: true` to an entailment check, a source lookup, or a judge.

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
