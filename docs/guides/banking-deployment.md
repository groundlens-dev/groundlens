# Production Deployment in Banking

This guide is for teams deploying groundlens as part of an AI
governance layer in a regulated banking environment. It covers the
end-to-end pipeline: triage of LLM outputs, audit log, compliance
mapping, calibration, and operational considerations specific to
US / EU bank deployments.

The patterns below are the deployment shape groundlens is designed
for. Each component (rules, audit, calibration, compliance) can be
adopted independently; they compose well when used together.

## Architectural overview

```
┌─────────────────────────────────────────────────────────────────┐
│                  LLM-powered banking workflow                   │
│         (credit decision, AML review, KYC, fraud, ...)          │
└────────────────────────────┬────────────────────────────────────┘
                             │ (question, response, context)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  groundlens triage layer                        │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │  SGI/DGI   │  │  Rule-based  │  │  Hybrid quality score  │   │
│  │  scoring   │  │  sub-scores  │  │  (geometric × rules)   │   │
│  └────────────┘  └──────────────┘  └────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
            ┌────────────────┴──────────────────┐
            ▼                                   ▼
┌────────────────────────┐         ┌────────────────────────────┐
│  Flagged → human       │         │  AuditLog (sqlite +        │
│  review queue          │         │  hash chain)               │
└────────────────────────┘         └────────────────────────────┘
                                             │
                                             ▼
                                   ┌────────────────────────┐
                                   │  Examiner exports +    │
                                   │  compliance reports    │
                                   └────────────────────────┘
```

## Minimum viable pipeline

The shortest production pipeline that covers triage + audit looks like:

```python
from groundlens import compute_sgi
from groundlens.rules import banking_rules
from groundlens.audit import AuditLog

audit = AuditLog(db_path="/var/lib/groundlens/audit.sqlite")
rules = banking_rules(quality_floor=0.3)


def process_decision(case):
    """Process one LLM-produced banking decision."""
    # 1. Geometric grounding score
    sgi = compute_sgi(
        question=case["question"],
        context=case["context"],
        response=case["response"],
    )

    # 2. Rule-based interpretable sub-scores
    rs = rules.evaluate(
        question=case["question"],
        response=case["response"],
        context=case["context"],
        metadata={
            "flags_present": case.get("flags", []),
            "jurisdiction": case.get("jurisdiction"),
            "transaction_type": case.get("transaction_type"),
        },
    )

    # 3. Hybrid flagging: flag if either signal flags
    flagged = sgi.flagged or rs.flagged

    # 4. Persist to audit log (hash chain)
    audit.record(
        identifier=case["case_id"],
        method="hybrid",
        score=sgi.value,
        flagged=flagged,
        inputs={
            "question": case["question"],
            "context": case["context"],
            "response": case["response"],
        },
        metadata={
            "operator": case.get("operator"),
            "model_version": case.get("model_version"),
            "jurisdiction": case.get("jurisdiction"),
        },
        rule_results=[
            {
                "rule_id": r.rule_id,
                "sub_score": r.sub_score,
                "matched": r.matched,
                "evidence_span": r.evidence_span,
            }
            for r in rs.rule_results
        ],
    )

    return {
        "case_id": case["case_id"],
        "flagged": flagged,
        "sgi_value": sgi.value,
        "spec": rs.spec,
        "expl": rs.expl,
        "bshift": rs.bshift,
        "audit_explanation": rs.audit_explanation,
    }
```

## Why hybrid (geometric + rules)?

Geometric methods (SGI, DGI) and rule-based methods detect different
failure modes:

| Failure mode | Detected by SGI/DGI | Detected by rules |
|---|---|---|
| Response ignores context (RAG miss) | yes (Type I) | partially (rules need response to be specific to case) |
| Response invents content outside the topic | yes (Type II) | sometimes |
| Rationale lacks specificity (no case detail) | no | yes (`spec` sub-score) |
| Rationale lacks explanatory linkage | no | yes (`expl` sub-score) |
| Rationale lacks resolution path | no | yes (`bshift` sub-score) |
| Response cites fabricated parameters that look plausible | no | no (this is a Type III error — neither method catches it) |

The geometric methods alone can miss cases where the rationale is
plausibly written but uninformative to a human reviewer. The rule-based
sub-scores alone can miss cases where the response is structurally rich
but ignores the actual context provided. Together they cover more of
the failure surface.

For Type III errors, complement groundlens with claim-level fact-
checking on the outputs that pass both signals.

## Calibration for banking domain

A banking deployment supplies its own verified-grounded calibration
corpus via the ``reference_csv=`` argument:

```python
from groundlens import compute_dgi

result = compute_dgi(
    question="What triggers a SAR filing under the Bank Secrecy Act?",
    response=llm_output,
    reference_csv="/path/to/your/banking_calibration.csv",
)
```

If no ``reference_csv`` is passed, ``compute_dgi`` falls back to the
bundled cross-domain corpus (212 pairs across nine domains including
finance), which is a generic starting point — not a substitute for a
banking-specific corpus. Build a deployment-specific calibration
spanning the sub-domains relevant to your operating context (credit,
AML, KYC, fraud, sanctions, concentration, model risk). A starting
target is 100–200 pairs per sub-domain. Do **not** target AUROC > 0.9: with authorship and length held constant, the ceiling for this class of detector is in the high 0.6s. Calibrate to size your second stage, not to hit a number. Held-out evaluation on a
held-out test set drawn from the same distribution. See the
[domain calibration guide](domain-calibration.md) for the procedure.

**Calibration data sourcing:** for banking deployments, sources include
internal model validation test cases, compliance committee post-mortems
with the final-decision rationale, and synthetic pairs reviewed by a
compliance officer. Do not source from the deployment's own LLM outputs
unless they have been independently verified — calibrating against
unverified pairs causes the reference direction to drift toward the
LLM's own biases.

## Threshold tuning

The defaults are derived from research benchmarks. For banking
deployments, the appropriate tuning depends on risk tier:

```python
from groundlens.rules import banking_rules

# Conservative — high-stakes paths (credit decisioning, sanctions screening)
strict_rules = banking_rules(quality_floor=0.4)

# Standard — medium-risk paths (KYC review, fraud triage)
standard_rules = banking_rules(quality_floor=0.3)

# Permissive — low-stakes paths (customer service, content moderation)
relaxed_rules = banking_rules(quality_floor=0.2)
```

Document the chosen threshold and the rationale in the deployment's
model inventory entry, per SR 11-7 §7.

## Deployment-specific rule extensions

Beyond the bundled `banking_rules()`, deployments often add a small
number of rules specific to their internal policy:

```python
from groundlens.rules import banking_rules, ChecklistRule, RuleEvidence

# Start from the bundled banking ruleset
base = banking_rules()

# Add an internal-policy rule, e.g. "rationale must cite the policy clause"
def _check_policy_clause(question, response, context, metadata):
    matched = "policy clause" in response.lower() or "internal policy" in response.lower()
    return RuleEvidence(matched=matched, span="policy clause", explanation="cites internal policy")

internal_rule = ChecklistRule(
    id="spec.internal_policy",
    description="cites internal policy clause",
    weight=0.15,
    sub_score="spec",
    check=_check_policy_clause,
)

# Compose a new ruleset
from groundlens.rules import RuleSet

deployment_rules = RuleSet(
    name="banking_internal_v1",
    rules=base.rules + (internal_rule,),
    quality_floor=base.quality_floor,
)
```

Version the ruleset (here `banking_internal_v1`) and tag the audit
log entries with the ruleset version in metadata. Any change to the
rule set is then visible in the audit trail.

## Self-hosted deployment

Banking environments typically require self-hosted deployment, not SaaS.
groundlens has no required external services:

- The embedding model (`all-MiniLM-L6-v2`, 80MB) ships with
  `sentence-transformers` and can be cached locally or in an internal
  artifact registry.
- The audit log uses SQLite, which is single-file and embeddable.
- No outbound network calls during scoring.

A minimum container build looks like:

```dockerfile
FROM python:3.12-slim

# Pre-fetch the embedding model into the image
RUN pip install --no-cache-dir groundlens \
    && python -c "from sentence_transformers import SentenceTransformer; \
       SentenceTransformer('all-MiniLM-L6-v2')"

# Audit log volume mount
VOLUME ["/var/lib/groundlens"]

ENV GROUNDLENS_AUDIT_DB=/var/lib/groundlens/audit.sqlite
```

## Examiner readiness checklist

When an examiner requests evidence for a banking AI governance review,
the following should be exportable in minutes:

- [x] **Audit log integrity** — `log.verify_chain()` reports valid.
- [x] **Period export** — `log.export_jsonl()` produces a JSONL file
      covering the examined period, with every input, output,
      configuration, and hash for every evaluation.
- [x] **Compliance mapping** — `from groundlens.compliance import
      all_mappings; all_mappings()` returns the documented design
      intent against SR 11-7 / EU AI Act / NIST AI RMF.
- [x] **Compliance report** — `ComplianceReport.to_markdown()`
      generates an examiner-ready report combining summary statistics
      with explicit clause references.
- [x] **Source code** — groundlens is Apache-2.0 licensed and the full
      source is available at the published version of the deployment.
- [x] **Calibration corpus** — the reference_csv used for DGI is
      stored alongside the deployment and version-controlled.

Run this checklist before any scheduled examination. If any item is
not green, the deployment is not examiner-ready.

## Performance and scale

Per-evaluation latency on a single CPU core:

| Method | Latency | Memory |
|---|---|---|
| SGI (with cached model) | 5-15 ms | ~150 MB resident |
| DGI (with cached model) | 5-15 ms | ~150 MB resident |
| Rules only | <1 ms | <1 MB additional |
| Audit log record | 0.5-2 ms | per-write |

For batch throughput: 100-200 evaluations per second per worker on
commodity hardware. Horizontal scaling is trivial because the scorer
is stateless; the audit log is the only shared component and SQLite
supports the concurrent reader patterns common in monitoring.

## Known limitations for banking deployment

Document the following in the deployment's model validation report:

1. **Type III errors** — embedding-based methods do not detect
   within-frame factual errors. Pair with claim-level fact-checking
   for high-stakes paths.
2. **Calibration scope** — the DGI calibration reflects the corpus
   used. Outside the calibrated domain, DGI degrades to general-
   purpose detection.
3. **Single-writer audit log** — SQLite-backed audit log supports
   single-writer single-process semantics. For multi-process
   deployments, split into per-process logs and reconcile downstream.
4. **Determinism contract** — determinism holds against a fixed
   embedding model version. Embedding model upgrades require re-
   calibration and a documented re-validation per SR 11-7 §3.

## References

- Marin, J. (2025). *Semantic Grounding Index for LLM Hallucination
  Detection.* arXiv:2512.13771.
- Marin, J. (2026). *A Geometric Taxonomy of Hallucinations in Large
  Language Models.* arXiv:2602.13224v3.
- Board of Governors of the Federal Reserve System and Office of the
  Comptroller of the Currency. *Supervisory Guidance on Model Risk
  Management* (SR 11-7). 2011.
- European Parliament and Council. *Regulation (EU) 2024/1689 on
  Artificial Intelligence (EU AI Act).* 2024.
- NIST. *AI Risk Management Framework 1.0.* 2023.
