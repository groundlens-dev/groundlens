"""Custom rule set example: legal contract review.

Demonstrates how to build a domain-specific rule set with `groundlens.rules`
when the bundled `groundlens_banking_rules` doesn't fit your use case.

The `RuleSet` engine is domain-agnostic:

- `ChecklistRule` is a single deterministic check on a (question, response,
  context, metadata) tuple. Returns `RuleEvidence` recording what matched
  and why.
- `RuleSet` groups rules under a name and a list of sub-score categories.
  An optional `flag_predicate` decides whether the aggregated result is
  flagged for human review (default: spec or expl below quality_floor —
  configurable per ruleset).
- Each rule carries a `citation` field so the audit trail records the
  academic, industrial, or regulatory source that motivates the rule.

This example builds a 6-rule set for legal contract review with two
sub-scores (groundedness, traceability) and a non-compensatory flag
predicate. Adapt the checks and citations to your domain.

Run with::

    python examples/custom_rules.py
"""

from __future__ import annotations

import re

from groundlens import ChecklistRule, RuleEvidence, RuleSet

# ── Domain-specific check functions ─────────────────────────────────────────


def check_cites_clause(question, response, context, metadata):
    """Does the rationale cite a specific contract clause?"""
    matched = bool(
        re.search(r"\b(clause|article|section|§)\s+\d+", response, re.IGNORECASE)
    )
    return RuleEvidence(
        matched=matched,
        span="clause/article/section",
        explanation="rationale cites a specific contract clause or article",
    )


def check_grounded_in_contract(question, response, context, metadata):
    """Does the rationale use vocabulary that overlaps with the contract context?"""
    if not context:
        return RuleEvidence(
            matched=True, span="", explanation="no contract context provided — abstains"
        )
    resp_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", response.lower()))
    ctx_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", context.lower()))
    if not resp_words:
        return RuleEvidence(matched=True, span="", explanation="no content words to verify")
    overlap = len(resp_words & ctx_words) / len(resp_words)
    matched = overlap >= 0.4
    return RuleEvidence(
        matched=matched,
        span=f"overlap={overlap:.2f}",
        explanation="rationale content overlaps the contract",
    )


def check_identifies_party(question, response, context, metadata):
    """Does the rationale identify which contracting party is affected?"""
    matched = any(
        word in response.lower()
        for word in ("party", "counterparty", "buyer", "seller", "licensor", "licensee")
    )
    return RuleEvidence(
        matched=matched,
        span="party reference",
        explanation="rationale identifies which contracting party is affected",
    )


def check_expresses_uncertainty(question, response, context, metadata):
    """Does the rationale hedge when the contract is silent or ambiguous?"""
    hedging_markers = (" may ", " might ", "suggests", "appears", "likely", "unclear")
    matched = any(marker in response.lower() for marker in hedging_markers)
    return RuleEvidence(
        matched=matched,
        span="hedging language",
        explanation="rationale hedges appropriately on ambiguous clauses",
    )


def check_governing_law_named(question, response, context, metadata):
    """Does the rationale name the governing law or jurisdiction?"""
    matched = any(
        marker in response.lower()
        for marker in ("governing law", "jurisdiction", "applicable law", "venue")
    )
    return RuleEvidence(
        matched=matched,
        span="governing law",
        explanation="rationale names the governing law or jurisdiction",
    )


def check_substantive_length(question, response, context, metadata):
    """Does the rationale provide a substantive natural-language justification?"""
    matched = len(response.split()) >= 25
    return RuleEvidence(
        matched=matched,
        span=f"tokens={len(response.split())}",
        explanation="rationale provides a substantive natural-language justification",
    )


# ── Custom flag predicate ───────────────────────────────────────────────────


def legal_flag_predicate(sub_scores: dict[str, float]) -> bool:
    """Flag when groundedness < 0.5 or traceability < 0.4.

    Legal rationales without a clause citation or without contract-grounded
    language are non-defensible regardless of how well written they are.
    """
    return sub_scores.get("groundedness", 0.0) < 0.5 or sub_scores.get("traceability", 0.0) < 0.4


# ── The rule set ─────────────────────────────────────────────────────────────


def legal_contract_rules() -> RuleSet:
    """A minimal rule set for legal contract review rationales."""
    rules = (
        # Groundedness — anchored in the contract
        ChecklistRule(
            id="legal.grounded_in_contract",
            description="rationale vocabulary overlaps the contract",
            weight=0.50,
            sub_score="groundedness",
            check=check_grounded_in_contract,
            citation=(
                "ABA Model Rules of Professional Conduct, Rule 1.1 Competence; "
                "RAGAs (Es et al., EACL 2024) §3 Faithfulness (adapted)"
            ),
        ),
        ChecklistRule(
            id="legal.identifies_party",
            description="rationale identifies which contracting party is affected",
            weight=0.30,
            sub_score="groundedness",
            check=check_identifies_party,
            citation="Restatement (Second) of Contracts §17 — Requirement of a Bargain",
        ),
        ChecklistRule(
            id="legal.expresses_uncertainty",
            description="rationale hedges on ambiguous clauses",
            weight=0.20,
            sub_score="groundedness",
            check=check_expresses_uncertainty,
            citation="ABA Model Rules of Professional Conduct, Rule 2.1 Advisor",
        ),
        # Traceability — auditable trail
        ChecklistRule(
            id="legal.cites_clause",
            description="rationale cites a specific contract clause",
            weight=0.55,
            sub_score="traceability",
            check=check_cites_clause,
            citation=(
                "Bluebook 21st ed. Rule 12 (Statutes) and Rule 19 (Contracts); "
                "EU AI Act 2024/1689 Art. 13(3)(b)(iv) — explain output capability"
            ),
        ),
        ChecklistRule(
            id="legal.governing_law_named",
            description="rationale names the governing law or jurisdiction",
            weight=0.25,
            sub_score="traceability",
            citation="Restatement (Second) of Conflict of Laws §187",
            check=check_governing_law_named,
        ),
        ChecklistRule(
            id="legal.substantive_length",
            description="rationale provides a substantive natural-language justification",
            weight=0.20,
            sub_score="traceability",
            citation="e-SNLI (Camburu et al., NeurIPS 2018) — natural-language rationale",
            check=check_substantive_length,
        ),
    )

    return RuleSet(
        name="legal_contract_review_v1",
        rules=rules,
        sub_scores=("groundedness", "traceability"),
        flag_predicate=legal_flag_predicate,
    )


# ── Demo ─────────────────────────────────────────────────────────────────────


def main() -> None:
    """Evaluate a strong and a weak legal rationale against the custom rule set."""
    ruleset = legal_contract_rules()

    contract_excerpt = (
        "Section 4.2 Termination. Either party may terminate this agreement "
        "with 30 days written notice. Section 7.1 Governing Law. This agreement "
        "shall be governed by the laws of the State of Delaware. The licensee "
        "shall pay a termination fee of $50,000 if termination occurs within "
        "the first 12 months."
    )

    strong_rationale = (
        "The counterparty's termination request is valid under Section 4.2 with the "
        "required 30 days notice. However, because the termination occurs within the "
        "first 12 months, Section 7.1 governing-law provisions apply and the licensee "
        "may owe the $50,000 termination fee. The agreement appears to support this "
        "interpretation but the fee clause is ambiguous on partial-year proration."
    )

    weak_rationale = "Termination looks fine. No issues."

    for label, rationale in [("strong", strong_rationale), ("weak", weak_rationale)]:
        result = ruleset.evaluate(
            question="Is this termination notice valid and what are the financial implications?",
            response=rationale,
            context=contract_excerpt,
        )
        print(f"\n=== {label} rationale ===")
        print(f"Sub-scores: {result.sub_scores}")
        print(f"Quality: {result.quality:.3f}")
        print(f"Flagged: {result.flagged}")
        print(f"\n{result.audit_explanation}")


if __name__ == "__main__":
    main()
