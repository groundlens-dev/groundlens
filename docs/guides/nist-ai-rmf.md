# NIST AI RMF 1.0 Mapping

The NIST AI Risk Management Framework 1.0 (NIST AI 100-1, January 2023)
is a voluntary framework that organizes AI risk management around four
functions: **Govern**, **Map**, **Measure**, and **Manage**. Each function
is decomposed into categories and subcategories with concrete outcomes.

groundlens contributes to specific subcategories in all four functions.
This page maps the contributions explicitly so a deployment team can
include them in its NIST AI RMF profile.

## Why groundlens fits the AI RMF

The AI RMF emphasizes seven trustworthy AI characteristics: valid and
reliable, safe, secure and resilient, accountable and transparent,
explainable and interpretable, privacy-enhanced, and fair with managed
harmful bias. groundlens supports several:

| Trustworthy characteristic | groundlens contribution |
|---|---|
| Valid and reliable | Deterministic scoring with documented mathematical properties; reproducible results across runs and machines |
| Accountable and transparent | Hash-chain audit log; per-evaluation traceability of inputs, outputs, configuration |
| Explainable and interpretable | Rule-based sub-scores with evidence spans; geometric scores decomposable into distances and angles |
| Secure and resilient | The deterministic first stage removes a class of failure modes from the triage step (no judge-model drift or compromise in scoring); the second-stage judge runs only on escalations |

## GOVERN function

GOVERN focuses on organizational policies, accountability, and culture
that anticipate, identify, and manage AI risks.

### GOVERN 1.4 — Risk management activities are documented

groundlens makes risk management activities inspectable in code:

```python
from groundlens.compliance import all_mappings

for mapping in all_mappings():
    print(f"{mapping.fn_name}: {mapping.description}")
    for ref in mapping.references:
        print(f"  {ref.standard}: {', '.join(ref.clauses)}")
```

The mapping is declarative and version-controlled with the source; any
change to the documented intent is visible in the commit history.

### GOVERN 1.5 — Ongoing monitoring and review processes are in place

The audit log enables continuous monitoring:

```python
from groundlens.audit import AuditLog

log = AuditLog(db_path="production_audit.sqlite")

# Daily flagged-rate check fed to the monitoring dashboard
def daily_summary(date):
    entries = [e for e in log.entries() if e.timestamp_utc.startswith(date)]
    flagged = [e for e in entries if e.flagged]
    return {
        "date": date,
        "total": len(entries),
        "flagged": len(flagged),
        "flagged_rate": len(flagged) / len(entries) if entries else 0.0,
    }
```

Combine with the verify_chain method for periodic integrity checks
that document the chain has not been tampered with.

## MAP function

MAP contextualizes the AI system's risks within its operating
environment.

### MAP 2.3 — Context characterization

The DGI calibration corpus characterizes the operating context for
grounding verification:

```python
from groundlens import compute_dgi

# Pass reference_csv= to use a deployment-specific verified-grounded corpus.
# If omitted, compute_dgi falls back to the bundled cross-domain corpus
# (212 pairs across nine domains) as a generic starting point.
result = compute_dgi(
    question="What triggers a SAR filing under the Bank Secrecy Act?",
    response=llm_output,
    reference_csv="/path/to/your/banking_calibration.csv",
)
```

A regulated banking deployment should build its own verified-grounded
calibration corpus covering the sub-domains relevant to its operating
context (credit, AML, KYC, fraud, sanctions, concentration, model
risk). Deployments should
extend this with deployment-specific verified pairs to reflect their
exact operating context — see the
[domain calibration guide](domain-calibration.md).

### MAP 5.1 — Likelihood and magnitude of impact

groundlens surfaces a flag and a continuous score. The flag aligns
with the documented risk threshold; the score supports prioritized
review:

```python
from groundlens import evaluate

result = evaluate(question=q, response=r, context=ctx)

# Severity tier based on score, not just binary flag
if result.value < 0.5:
    severity = "high"
elif result.value < 0.95:
    severity = "medium"
else:
    severity = "low"
```

Document severity tiers in the deployment's NIST AI RMF profile so
human reviewers operate against a shared rubric.

## MEASURE function

MEASURE selects and applies appropriate metrics to identified risks.

### MEASURE 2.5 — Trustworthiness characteristics are evaluated

Each groundlens method tracks a specific trustworthiness dimension:

| Method | Trustworthy characteristic |
|---|---|
| SGI | Valid and reliable (does the response engage with the source?) |
| DGI | Valid and reliable (does the response follow grounded patterns?) |
| Rules (`spec`) | Explainable (does the response cite concrete case details?) |
| Rules (`expl`) | Explainable (does the response link facts to decision?) |
| Rules (`bshift`) | Accountable (does the response state what would resolve the case?) |

### MEASURE 2.7 — Performance is monitored against baselines

The bundled benchmark provides a published baseline:

```bash
groundlens benchmark --dataset cert-framework/human-confabulation-benchmark
```

Track per-batch metrics over time and alert on regression against the
deployment's own historical baseline:

```python
from collections import deque

window = deque(maxlen=30)  # 30-day rolling
window.append(daily_summary("2026-06-08"))

# Alert on rolling deviation
rates = [d["flagged_rate"] for d in window]
mean = sum(rates) / len(rates)
if window[-1]["flagged_rate"] > mean * 1.5:
    alert_oncall("flagged rate elevated 50% above 30d mean")
```

### MEASURE 4.2 — Operational metrics for monitoring

The audit log persists operational metrics per evaluation. Use this
for drift detection, capacity planning, and root-cause investigation
when a flagged rate jump is detected.

## MANAGE function

MANAGE allocates risk-related resources and treatments.

### MANAGE 4.1 — Risk treatment via flagged-output review

groundlens is explicitly a triage tool. Flagged outputs are routed to
human review; passed outputs are released:

```python
from groundlens import evaluate

result = evaluate(question=q, response=r, context=ctx)

if result.flagged:
    queue_for_human_review(case_id, result)
else:
    release_to_user(case_id, response)
```

The flagged rate is itself a managed metric: too low may indicate the
threshold is mis-tuned (false negatives); too high indicates excessive
human workload and may justify investment in upstream model improvements.

### MANAGE 4.3 — Incident management

For incident investigations, the audit log provides forensic-quality
evidence:

```python
from groundlens.audit import AuditLog

log = AuditLog(db_path="production_audit.sqlite")

# Reproduce the exact decision for a contested case
entry = next(e for e in log.entries() if e.identifier == "case_2026_06_05_123")
print(entry.payload_json)
print(f"Hash: {entry.entry_hash}")

# Verify the chain has not been altered around this entry
verification = log.verify_chain()
assert verification.valid
```

The hash chain provides cryptographic evidence the entry was not
modified between its original logging and the investigation.

## Known limitations for AI RMF profiling

Document the following in the deployment's AI RMF profile under MAP
5.1 and MANAGE 1.1:

1. **Type III errors not detectable.** Embedding-based methods cannot
   distinguish within-frame factual errors (e.g. "the capital of
   Australia is Sydney"). For high-stakes domains, complement with
   claim-level fact-checking on outputs that pass geometric triage.
2. **Calibration drift.** The DGI reference direction depends on the
   underlying language patterns of the calibration corpus. Schedule
   refresh in line with the deployment's risk appetite.
3. **Embedding model is a dependency.** The underlying sentence
   transformer (default: `all-MiniLM-L6-v2`) is a component of the
   measurement system. Include it in the model inventory and version-
   pin it.

## References

- NIST. *AI Risk Management Framework (AI RMF 1.0)*. NIST AI 100-1.
  January 2023.
  [nist.gov/itl/ai-risk-management-framework](https://www.nist.gov/itl/ai-risk-management-framework)
- Marin, J. (2025). *Semantic Grounding Index for LLM Hallucination
  Detection.* arXiv:2512.13771.
- Marin, J. (2026). *A Geometric Taxonomy of Hallucinations in Large
  Language Models.* arXiv:2602.13224v3.
