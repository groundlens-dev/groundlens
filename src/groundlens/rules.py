"""Rule-based interpretable layer — deterministic, auditable, no LLM.

This module provides a checklist-style rule engine that complements the
geometric SGI/DGI scores with human-readable audit evidence. A trained
auditor or compliance officer can read the textual explanation produced
by a :class:`RuleSet` evaluation and verify, item by item, why a response
passed or failed.

The rule engine is intentionally rule-based rather than learning-based:

- **Deterministic.** Same inputs → same outputs, byte-identical.
- **Auditable.** Every pass/fail decision cites the rule, the weight, and
  the matched evidence span in the response text.
- **No LLM.** Pattern matching, substring tests, and regular expressions.
  Compatible with the no-second-LLM constraint of groundlens.
- **Domain-specific.** Built-in factories (:func:`banking_rules`) exist
  for regulated domains; custom rule sets can be assembled from
  :class:`ChecklistRule` instances or loaded from configuration.

Sub-scores follow the structure of compliance rationale evaluation in
regulated AI literature: **specificity** (does the response cite concrete
case details?), **explanatory linkage** (does it explain the reasoning?),
and **boundary shift** (does it state what would resolve the case?).
Each is in [0, 1] and aggregated via a non-compensatory geometric mean
so a zero sub-score collapses the overall quality signal — a rationale
that names parameters but offers no resolution path is *not* partial
credit, it is structurally incomplete.

References:
    Toulmin, S. E. (2003). *The Uses of Argument*. Cambridge University Press.

    McCarthy, P. M., & Jarvis, S. (2010). MTLD, vocd-D, and HD-D: A validation
        study of sophisticated approaches to lexical diversity assessment.
        *Behavior Research Methods*, 42(2), 381-392.

    Karwowski, J., et al. (2024). Goodhart's Law in Reinforcement Learning.
        *ICLR 2024*.

    De la Chica Rodríguez, J. M., & Martí-González, C. (2026). Mechanical
        Enforcement for LLM Governance. arXiv:2605.14744.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

# ── Public types ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RuleEvidence:
    """A single piece of evidence supporting a rule's pass/fail decision.

    Attributes:
        matched: Whether the rule pattern matched the input text.
        span: The substring (lowercased) that triggered the match, or
            ``""`` if no match was found.
        explanation: Short human-readable note describing what was checked.
    """

    matched: bool
    span: str
    explanation: str


@dataclass(frozen=True, slots=True)
class ChecklistRule:
    """A single rule with an id, a pattern check, and a weight.

    Rules are designed to be readable: ``id`` and ``description`` are
    surfaced verbatim in the audit explanation. The ``check`` callable
    returns a :class:`RuleEvidence` so the audit trail records *why* the
    rule fired, not just *that* it did.

    Attributes:
        id: Stable identifier (e.g. ``"spec.reg_flag"``). Used in audit logs.
        description: One-line human-readable description of the rule.
        weight: Contribution to the parent sub-score when matched, in [0, 1].
            Sub-scores are capped at 1.0 even when weights sum higher.
        sub_score: Which sub-score this rule contributes to: ``"spec"``,
            ``"expl"``, or ``"bshift"``.
        check: Pure function ``(question, response, context, metadata)
            -> RuleEvidence``. Must be deterministic.
    """

    id: str
    description: str
    weight: float
    sub_score: str
    check: Callable[[str, str, str | None, dict[str, Any]], RuleEvidence]


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Outcome of evaluating a single rule.

    Attributes:
        rule_id: The :attr:`ChecklistRule.id` that produced this result.
        sub_score: Which sub-score this rule contributes to.
        weight: The weight of the rule (echo of :attr:`ChecklistRule.weight`).
        matched: Whether the rule fired.
        evidence_span: The substring that triggered the match, if any.
        explanation: The rule's human-readable explanation.
    """

    rule_id: str
    sub_score: str
    weight: float
    matched: bool
    evidence_span: str
    explanation: str


@dataclass(frozen=True, slots=True)
class RuleSetResult:
    """Aggregated result of evaluating a :class:`RuleSet` against a response.

    The three sub-scores (``spec``, ``expl``, ``bshift``) are computed as
    capped weight sums of matched rules in each category. ``quality`` is
    the geometric mean of the three sub-scores: any zero sub-score yields
    ``quality = 0.0``, reflecting that a rationale missing any of
    specificity / explanatory linkage / boundary shift is structurally
    incomplete for human review.

    Attributes:
        spec: Specificity sub-score in [0, 1].
        expl: Explanatory linkage sub-score in [0, 1].
        bshift: Boundary shift sub-score in [0, 1].
        quality: Geometric mean ``(spec * expl * bshift) ** (1/3)``.
        flagged: ``True`` if either spec or expl falls below the cosmetic-
            deadlock threshold (default 0.3), indicating an audit-deficient
            rationale.
        rule_results: One :class:`RuleResult` per rule that was evaluated.
        audit_explanation: Multi-line human-readable summary suitable for
            inclusion in an audit log.
    """

    spec: float
    expl: float
    bshift: float
    quality: float
    flagged: bool
    rule_results: tuple[RuleResult, ...]
    audit_explanation: str


# ── Threshold constants (overridable per RuleSet) ───────────────────────────


_DEFAULT_QUALITY_FLOOR: float = 0.3
"""Sub-score threshold below which the rationale is considered cosmetically
deficient. Conservative default; tune per deployment.
"""


# ── RuleSet ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RuleSet:
    """A collection of rules evaluated together against a (q, r, ctx) triple.

    Use :func:`banking_rules` for a curated regulated-finance ruleset, or
    construct your own by passing a sequence of :class:`ChecklistRule`.

    Attributes:
        name: Identifier (e.g. ``"banking_v1"``). Surfaced in audit logs.
        rules: The rules to evaluate.
        quality_floor: Threshold below which a sub-score triggers the
            cosmetic-deadlock flag. Default ``0.3``.
    """

    name: str
    rules: tuple[ChecklistRule, ...]
    quality_floor: float = _DEFAULT_QUALITY_FLOOR

    def evaluate(
        self,
        *,
        question: str,
        response: str,
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuleSetResult:
        """Evaluate the ruleset against a single (question, response) pair.

        Args:
            question: The user query / prompt the LLM received.
            response: The LLM's rationale text being audited.
            context: Optional retrieved context (RAG-style). May be ``None``
                when no retrieval was performed.
            metadata: Optional dict carrying domain-specific structured data
                that some rules may consult (e.g. the case parameters in a
                banking decision: risk score, flags, amount, etc.).

        Returns:
            A :class:`RuleSetResult` with all sub-scores, the aggregated
            quality, and a full audit explanation.

        Raises:
            ValueError: If ``response`` is empty.
        """
        if not response.strip():
            msg = "response must be a non-empty string."
            raise ValueError(msg)

        meta = metadata or {}

        results: list[RuleResult] = []
        weights_by_sub: dict[str, float] = {"spec": 0.0, "expl": 0.0, "bshift": 0.0}

        for rule in self.rules:
            evidence = rule.check(question, response, context, meta)
            results.append(
                RuleResult(
                    rule_id=rule.id,
                    sub_score=rule.sub_score,
                    weight=rule.weight,
                    matched=evidence.matched,
                    evidence_span=evidence.span,
                    explanation=evidence.explanation,
                )
            )
            if evidence.matched and rule.sub_score in weights_by_sub:
                weights_by_sub[rule.sub_score] += rule.weight

        spec = min(1.0, weights_by_sub["spec"])
        expl = min(1.0, weights_by_sub["expl"])
        bshift = min(1.0, weights_by_sub["bshift"])
        quality = float((spec * expl * bshift) ** (1.0 / 3.0)) if spec * expl * bshift > 0 else 0.0
        flagged = (spec < self.quality_floor) or (expl < self.quality_floor)

        audit = _format_audit_explanation(
            ruleset_name=self.name,
            spec=spec,
            expl=expl,
            bshift=bshift,
            quality=quality,
            flagged=flagged,
            quality_floor=self.quality_floor,
            results=results,
        )

        return RuleSetResult(
            spec=round(spec, 4),
            expl=round(expl, 4),
            bshift=round(bshift, 4),
            quality=round(quality, 4),
            flagged=flagged,
            rule_results=tuple(results),
            audit_explanation=audit,
        )


# ── Audit explanation formatter ─────────────────────────────────────────────


def _format_audit_explanation(
    *,
    ruleset_name: str,
    spec: float,
    expl: float,
    bshift: float,
    quality: float,
    flagged: bool,
    quality_floor: float,
    results: Sequence[RuleResult],
) -> str:
    """Render a multi-line audit explanation suitable for log inclusion."""
    lines: list[str] = []
    lines.append(f"Ruleset: {ruleset_name}")
    lines.append(
        f"Sub-scores: spec={spec:.3f}, expl={expl:.3f}, bshift={bshift:.3f} "
        f"(quality={quality:.3f})"
    )
    verdict = "FLAGGED" if flagged else "PASS"
    lines.append(f"Verdict: {verdict} (cosmetic-deadlock threshold={quality_floor})")

    matched = [r for r in results if r.matched]
    missed = [r for r in results if not r.matched]

    if matched:
        lines.append("Matched rules:")
        for r in matched:
            snippet = f" — evidence: '{r.evidence_span}'" if r.evidence_span else ""
            lines.append(f"  [{r.rule_id}] {r.explanation} (+{r.weight:.2f}){snippet}")

    if missed:
        lines.append("Unmatched rules:")
        for r in missed:
            lines.append(f"  [{r.rule_id}] {r.explanation}")

    return "\n".join(lines)


# ── Pattern matching helpers (pure, deterministic) ──────────────────────────


def _lower(text: str) -> str:
    return text.lower()


def _matches_any(text: str, needles: Iterable[str]) -> RuleEvidence:
    """Return evidence for the first matching needle (case-insensitive)."""
    lowered = _lower(text)
    for needle in needles:
        if needle.lower() in lowered:
            return RuleEvidence(matched=True, span=needle.lower(), explanation="")
    return RuleEvidence(matched=False, span="", explanation="")


def _matches_regex(text: str, pattern: re.Pattern[str]) -> RuleEvidence:
    """Return evidence for the first regex match."""
    match = pattern.search(text)
    if match is None:
        return RuleEvidence(matched=False, span="", explanation="")
    return RuleEvidence(matched=True, span=match.group(0)[:80], explanation="")


_NUMERIC_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_GATE_NAME_RE = re.compile(r"\bK\d_\d+\b|\bgate\b|\bthreshold\b", re.IGNORECASE)


# ── Banking ruleset ─────────────────────────────────────────────────────────


_BANKING_FLAGS: tuple[str, ...] = (
    "AML",
    "KYC",
    "SANCTIONS",
    "INSIDER",
    "CONCENTRATION",
)


def _check_regulatory_flag(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response cite a regulatory flag present in the case metadata?"""
    flags_in_case: list[str] = list(metadata.get("flags_present", _BANKING_FLAGS))
    explanation = "Mentions a regulatory flag relevant to the case"
    ev = _matches_any(response, flags_in_case)
    return RuleEvidence(matched=ev.matched, span=ev.span, explanation=explanation)


def _check_risk_reference(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response reference a risk score or risk concept?"""
    ev = _matches_any(response, ["risk score", "risk level", "risk indicator", "risk"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="References risk score or risk concept"
    )


def _check_numeric_value(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response include a numeric value (case parameter or threshold)?"""
    ev = _matches_regex(response, _NUMERIC_RE)
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Includes a numeric value"
    )


def _check_gate_name(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response name a specific gate or threshold rule?"""
    ev = _matches_regex(response, _GATE_NAME_RE)
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Names a gate or threshold by identifier"
    )


def _check_information_gap(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response identify a missing-information gap?"""
    ev = _matches_any(
        response,
        ["completeness", "missing", "incomplete", "information gap", "documentation"],
    )
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Names an information gap"
    )


def _check_case_specific_detail(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response cite a case-specific contextual detail?"""
    needles = [
        "counterparty",
        "amount",
        "transaction",
        "tenure",
        "jurisdiction",
        str(metadata.get("jurisdiction", "")).lower() if metadata.get("jurisdiction") else "",
        str(metadata.get("transaction_type", "")).replace("_", " ").lower()
        if metadata.get("transaction_type")
        else "",
    ]
    needles = [n for n in needles if n]
    ev = _matches_any(response, needles)
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Cites a case-specific contextual detail"
    )


def _check_substantive_length(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response provide substantive length (> 30 tokens)?"""
    matched = len(response.split()) > 30
    return RuleEvidence(
        matched=matched, span="", explanation="Substantive length (> 30 tokens)"
    )


def _check_specificity_language(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response use specificity-marking language?"""
    ev = _matches_any(response, ["specifically", "in particular"])
    return RuleEvidence(
        matched=ev.matched,
        span=ev.span,
        explanation="Uses specificity-marking language",
    )


def _check_conditional_structure(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response use conditional structure (if / because / cannot)?"""
    ev = _matches_any(response, ["if ", "because", "cannot"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Uses conditional or causal structure"
    )


def _check_pending_action(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response name a pending action?"""
    ev = _matches_any(response, ["pending", "awaiting"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Names a pending action"
    )


def _check_causal_connective(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response use an explicit causal connective?"""
    ev = _matches_any(response, ["due to", "consequently", "therefore"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Uses an explicit causal connective"
    )


def _check_epistemic_limit(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response state an epistemic limitation?"""
    ev = _matches_any(
        response, ["cannot determine", "insufficient", "unable to"]
    )
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="States an epistemic limitation"
    )


def _check_domain_reference(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response reference a domain concept (compliance / regulatory)?"""
    ev = _matches_any(response, ["compliance", "regulatory", "policy", "flag"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="References a domain concept"
    )


def _check_modal_verb(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response use a modal verb (would/should/need)?"""
    ev = _matches_any(response, ["would", "should", "need"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Uses a modal verb"
    )


def _check_minimum_length(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response meet minimum length (> 20 tokens)?"""
    matched = len(response.split()) > 20
    return RuleEvidence(matched=matched, span="", explanation="Minimum length (> 20 tokens)")


def _check_temporal_ordering(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response include temporal ordering (before / prior to / until)?"""
    ev = _matches_any(response, ["before", "prior to", "until"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Includes temporal ordering"
    )


def _check_conditional_approval(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response state a conditional approval pathway?"""
    ev = _matches_any(
        response,
        ["would approve if", "would change", "favorable resolution"],
    )
    return RuleEvidence(
        matched=ev.matched,
        span=ev.span,
        explanation="States a conditional approval pathway",
    )


def _check_information_request(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response request additional information?"""
    ev = _matches_any(
        response, ["additional information", "further documentation", "more data"]
    )
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Requests additional information"
    )


def _check_risk_reduction(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response propose risk-reduction language?"""
    ev = _matches_any(response, ["risk reduction", "mitigate", "reduce risk"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Proposes risk-reduction language"
    )


def _check_alternative_framing(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response offer an alternative framing?"""
    ev = _matches_any(response, ["otherwise", "alternatively"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Offers an alternative framing"
    )


def _check_threshold_reference(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response reference a standard / threshold / criterion?"""
    ev = _matches_any(response, ["standard", "threshold", "criteria"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="References a threshold or criterion"
    )


def _check_resolution_length(
    question: str,  # noqa: ARG001
    response: str,
    context: str | None,  # noqa: ARG001
    metadata: dict[str, Any],  # noqa: ARG001
) -> RuleEvidence:
    """Did the response have substantive length for resolution path (> 25 tokens)?"""
    matched = len(response.split()) > 25
    return RuleEvidence(
        matched=matched, span="", explanation="Substantive resolution-path length (> 25 tokens)"
    )


def banking_rules(quality_floor: float = _DEFAULT_QUALITY_FLOOR) -> RuleSet:
    """Curated ruleset for regulated banking governance decisions.

    The rules cover the three sub-scores that an auditor or compliance
    officer typically inspects in a deferral or escalation rationale:

    - **Specificity (spec):** does the rationale cite the case parameters
      that triggered the decision? Flags, risk score, numeric thresholds,
      gates, completeness, jurisdictional details, sufficient length, and
      specificity-marking language.
    - **Explanatory linkage (expl):** does the rationale link the case
      facts to the decision? Conditional structure, pending actions, causal
      connectives, epistemic limits, domain references, modal verbs,
      length, and temporal ordering.
    - **Boundary shift (bshift):** does the rationale state what would
      change the decision? Conditional approval pathways, information
      requests, risk-reduction proposals, alternative framings, threshold
      references, and length.

    The default ``quality_floor=0.3`` follows the cosmetic-deadlock
    threshold introduced in the financial-decisions governance literature.
    A response that falls below this floor on either ``spec`` or ``expl``
    is flagged as audit-deficient even if the geometric SGI/DGI score
    looks acceptable in isolation — a structurally typical "false
    negative" of embedding-based detection.

    Args:
        quality_floor: Threshold below which a sub-score triggers the
            cosmetic-deadlock flag. Tune per deployment risk tolerance.

    Returns:
        A :class:`RuleSet` named ``"banking_v1"``.
    """
    rules: tuple[ChecklistRule, ...] = (
        # Specificity sub-rules
        ChecklistRule("spec.reg_flag", "regulatory flag", 0.20, "spec", _check_regulatory_flag),
        ChecklistRule("spec.risk_ref", "risk reference", 0.15, "spec", _check_risk_reference),
        ChecklistRule("spec.numeric", "numeric value", 0.10, "spec", _check_numeric_value),
        ChecklistRule("spec.gate", "gate / threshold", 0.10, "spec", _check_gate_name),
        ChecklistRule(
            "spec.info_gap", "information gap", 0.15, "spec", _check_information_gap
        ),
        ChecklistRule(
            "spec.case_detail", "case-specific detail", 0.10, "spec", _check_case_specific_detail
        ),
        ChecklistRule("spec.length", "substantive length", 0.10, "spec", _check_substantive_length),
        ChecklistRule(
            "spec.spec_language",
            "specificity language",
            0.10,
            "spec",
            _check_specificity_language,
        ),
        # Explanatory linkage sub-rules
        ChecklistRule(
            "expl.conditional", "conditional structure", 0.20, "expl", _check_conditional_structure
        ),
        ChecklistRule("expl.pending", "pending action", 0.15, "expl", _check_pending_action),
        ChecklistRule(
            "expl.causal", "causal connective", 0.15, "expl", _check_causal_connective
        ),
        ChecklistRule(
            "expl.epistemic", "epistemic limitation", 0.15, "expl", _check_epistemic_limit
        ),
        ChecklistRule("expl.domain", "domain reference", 0.10, "expl", _check_domain_reference),
        ChecklistRule("expl.modal", "modal verb", 0.10, "expl", _check_modal_verb),
        ChecklistRule("expl.length", "minimum length", 0.10, "expl", _check_minimum_length),
        ChecklistRule(
            "expl.temporal", "temporal ordering", 0.05, "expl", _check_temporal_ordering
        ),
        # Boundary shift sub-rules
        ChecklistRule(
            "bshift.cond_approval",
            "conditional approval",
            0.25,
            "bshift",
            _check_conditional_approval,
        ),
        ChecklistRule(
            "bshift.info_request",
            "information request",
            0.20,
            "bshift",
            _check_information_request,
        ),
        ChecklistRule(
            "bshift.risk_reduction", "risk reduction", 0.15, "bshift", _check_risk_reduction
        ),
        ChecklistRule(
            "bshift.alternative", "alternative framing", 0.10, "bshift", _check_alternative_framing
        ),
        ChecklistRule(
            "bshift.threshold_ref",
            "threshold reference",
            0.10,
            "bshift",
            _check_threshold_reference,
        ),
        ChecklistRule(
            "bshift.length", "resolution-path length", 0.05, "bshift", _check_resolution_length
        ),
    )
    return RuleSet(name="banking_v1", rules=rules, quality_floor=quality_floor)


__all__ = [
    "ChecklistRule",
    "RuleEvidence",
    "RuleResult",
    "RuleSet",
    "RuleSetResult",
    "banking_rules",
]
