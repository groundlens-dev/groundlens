# EU AI Act Compliance

The EU AI Act (Regulation 2024/1689) imposes requirements on AI systems, particularly those classified as high-risk. groundlens is designed to help organizations meet several of these requirements through its deterministic, auditable architecture.

## Why groundlens Helps with Compliance

The EU AI Act requires that high-risk AI systems be:

1. **Transparent**: Users must be able to understand how the system makes decisions.
2. **Auditable**: The decision-making process must be reproducible and inspectable.
3. **Monitored**: Ongoing quality assurance must be in place.
4. **Documented**: Technical documentation must describe the system's capabilities and limitations.

groundlens supports all four requirements by design.

## A Deterministic First Stage

The usual pattern, "LLM-as-judge", uses a second LLM to evaluate the first. It is not the alternative to groundlens; it is the **second stage**. But run on everything, on its own, it creates compliance problems:

| Issue | LLM-as-Judge | groundlens |
|---|---|---|
| Determinism | Non-deterministic (sampling) | Deterministic (same inputs = same score) |
| Auditability | Opaque (why did the judge say "correct"?) | Transparent (distance ratio or cosine similarity) |
| Reproducibility | Varies across runs, model versions | Exact reproduction given same model and inputs |
| Cost | Requires LLM inference per evaluation | Sentence-transformer inference only |
| Circular risk | The judge LLM can itself hallucinate | No generative model in the evaluation loop |

!!! abstract "Key compliance advantage"
    groundlens removes the generative model from the **triage** step. The score is computed via deterministic mathematical operations on embeddings: no sampling, no temperature, no prompt sensitivity.

    It does not remove the second stage, and it should not. What it gives an examiner is a deterministic, reproducible account of **which** outputs were escalated to the judge and **why**.

!!! danger "What determinism does not buy you (Article 15)"
    Coverage. A confabulation that stays in register, right topic, right terminology, one wrong figure, is close to invisible to any embedding-similarity method: the whole class tops out in the high 0.6s AUROC once authorship is controlled.

    Do not present a geometric score to an examiner as Article 15 accuracy evidence on its own. Under **Article 9**, however, a method that publishes its own failure region as a number rather than a caveat is worth more than one reporting a figure it cannot defend. Write the blind spot into the risk file.

## Article 9: Risk Management

The EU AI Act requires a risk management system that identifies and mitigates risks throughout the AI system's lifecycle.

**How groundlens helps**: Deploy groundlens as a continuous monitoring layer that flags high-risk outputs for human review. The flagging rate provides a quantitative risk metric that can be tracked over time.

```python
# Example: risk monitoring pipeline
from groundlens import evaluate

def risk_monitor(question, response, context=None):
    score = evaluate(question=question, response=response, context=context)
    return {
        "risk_level": "high" if score.flagged else "low",
        "score": score.value,
        "method": score.method,
        "explanation": score.explanation,
        "deterministic": True,
        "reproducible": True,
    }
```

## Article 13: Transparency

High-risk AI systems must provide "sufficient transparency to enable deployers to interpret the system's output."

**How groundlens helps**: Every groundlens score comes with:

- A numeric value with clear geometric meaning
- A human-readable explanation
- The method used (SGI or DGI)
- Intermediate values (distances, normalized scores) for full traceability

```python
score = evaluate(question="...", response="...", context="...")

# Full transparency chain
print(f"Method: {score.method}")
print(f"Raw score: {score.value}")
print(f"Normalized: {score.normalized}")
print(f"Flagged: {score.flagged}")
print(f"Explanation: {score.explanation}")

# For SGI, additional detail
if score.method == "sgi":
    print(f"Distance to question: {score.detail.q_dist}")
    print(f"Distance to context: {score.detail.ctx_dist}")
```

## Article 14: Human Oversight

The Act requires that high-risk AI systems include measures for effective human oversight.

**How groundlens helps**: groundlens is explicitly designed as a **triage tool** --- it identifies which outputs need human review, not which outputs are "correct." This keeps humans in the loop while reducing the volume they need to review.

| Without groundlens | With groundlens |
|---|---|
| Review 100% of outputs | Review ~20% of outputs (flagged) |
| Random or no prioritization | Prioritized by geometric risk score |
| No quantitative risk signal | Numeric score for risk ranking |

## Article 17: Quality Management

Organizations deploying high-risk AI must maintain a quality management system.

**How groundlens helps**: Use batch evaluation in CI/CD pipelines to gate deployments:

```bash
# In your CI pipeline
groundlens evaluate test_outputs.csv --output scored.csv

# Fail the deployment if flagged rate exceeds threshold
python -c "
import csv
with open('scored.csv') as f:
    rows = list(csv.DictReader(f))
    flagged = sum(1 for r in rows if r['groundlens_flagged'] == 'True')
    rate = flagged / len(rows)
    print(f'Flagged rate: {rate:.1%}')
    if rate > 0.10:
        print('FAIL: Flagged rate exceeds 10% threshold')
        exit(1)
"
```

## Audit Trail

For regulatory audits, log every groundlens evaluation:

```python
import json
import datetime
from groundlens import evaluate


def auditable_evaluate(question, response, context=None, **kwargs):
    score = evaluate(question=question, response=response, context=context, **kwargs)

    audit_record = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "inputs": {
            "question": question,
            "response": response,
            "context": context,
        },
        "outputs": {
            "method": score.method,
            "value": score.value,
            "normalized": score.normalized,
            "flagged": score.flagged,
            "explanation": score.explanation,
        },
        "config": {
            "model": kwargs.get("model", "all-MiniLM-L6-v2"),
            "reference_csv": kwargs.get("reference_csv"),
        },
    }

    # Write to audit log
    with open("groundlens_audit.jsonl", "a") as f:
        f.write(json.dumps(audit_record) + "\n")

    return score
```

## Known Limitations for Compliance

Be transparent about what groundlens does **not** guarantee:

1. **Not a factual truth detector**: groundlens measures geometric grounding, not factual accuracy. It cannot determine if "Paris is the capital of France" is true.
2. **Confabulation boundary**: Deliberately crafted false statements that mimic grounded patterns are not detectable (see [Confabulation Boundary](../theory/confabulation-boundary.md)).
3. **Threshold sensitivity**: The flagging thresholds are empirically derived and may need tuning for specific use cases.

!!! warning "Documentation requirement"
    When documenting groundlens for regulatory purposes, include these limitations explicitly. The EU AI Act values honest documentation of capabilities and limitations over claims of perfection.
