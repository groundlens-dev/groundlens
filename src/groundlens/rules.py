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
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

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
        sub_score: Which sub-score this rule contributes to. For the legacy
            ``banking_rules()`` set: ``"spec"``, ``"expl"``, or ``"bshift"``.
            For the current ``groundlens_banking_rules()`` set:
            ``"groundedness"``, ``"completeness"``, ``"calibration"``,
            ``"traceability"``, or ``"robustness"``. Custom rule sets may
            define additional categories.
        check: Pure function ``(question, response, context, metadata)
            -> RuleEvidence``. Must be deterministic.
        citation: Free-text academic / industry / regulatory provenance for
            the rule, suitable for inclusion in an audit explanation or a
            regulatory submission. Empty string when no citation is provided.
            Example: ``"RAGAs (Es et al., EACL 2024) §3 Faithfulness"``.
    """

    id: str
    description: str
    weight: float
    sub_score: str
    check: Callable[[str, str, str | None, dict[str, Any]], RuleEvidence]
    citation: str = ""


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

    Each sub-score is a capped weight sum of matched rules in that category,
    stored in the :attr:`sub_scores` mapping. ``quality`` is the geometric
    mean of all sub-score values: any zero sub-score yields ``quality = 0.0``,
    reflecting that a rationale missing any audited dimension is structurally
    incomplete for human review.

    Backward-compatible read accessors are exposed for the legacy De-La-Chica
    style sub-scores (``spec``, ``expl``, ``bshift``) and for the current
    GroundLens five-category skeleton (``groundedness``, ``completeness``,
    ``calibration``, ``traceability``, ``robustness``). Accessors return
    ``0.0`` when the underlying ruleset did not define the requested sub-score.

    Attributes:
        sub_scores: Mapping from sub-score name to its capped value in [0, 1].
            By convention, do not mutate.
        quality: Geometric mean of all sub-score values in :attr:`sub_scores`.
        flagged: ``True`` when the ruleset's flag predicate is triggered.
        rule_results: One :class:`RuleResult` per rule that was evaluated.
        audit_explanation: Multi-line human-readable summary suitable for
            inclusion in an audit log.
    """

    sub_scores: dict[str, float]
    quality: float
    flagged: bool
    rule_results: tuple[RuleResult, ...]
    audit_explanation: str

    # ── Legacy 3-category accessors (banking_rules / De La Chica skeleton)
    @property
    def spec(self) -> float:
        """Legacy specificity sub-score. Returns 0.0 if not defined by ruleset."""
        return self.sub_scores.get("spec", 0.0)

    @property
    def expl(self) -> float:
        """Legacy explanatory-linkage sub-score. Returns 0.0 if not defined by ruleset."""
        return self.sub_scores.get("expl", 0.0)

    @property
    def bshift(self) -> float:
        """Legacy boundary-shift sub-score. Returns 0.0 if not defined by ruleset."""
        return self.sub_scores.get("bshift", 0.0)

    # ── Current 5-category accessors (groundlens_banking_rules skeleton)
    @property
    def groundedness(self) -> float:
        """Groundedness sub-score. Returns 0.0 if not defined by ruleset."""
        return self.sub_scores.get("groundedness", 0.0)

    @property
    def completeness(self) -> float:
        """Completeness sub-score. Returns 0.0 if not defined by ruleset."""
        return self.sub_scores.get("completeness", 0.0)

    @property
    def calibration(self) -> float:
        """Calibration sub-score. Returns 0.0 if not defined by ruleset."""
        return self.sub_scores.get("calibration", 0.0)

    @property
    def traceability(self) -> float:
        """Traceability sub-score. Returns 0.0 if not defined by ruleset."""
        return self.sub_scores.get("traceability", 0.0)

    @property
    def robustness(self) -> float:
        """Robustness sub-score. Returns 0.0 if not defined by ruleset."""
        return self.sub_scores.get("robustness", 0.0)


# ── Threshold constants (overridable per RuleSet) ───────────────────────────


_DEFAULT_QUALITY_FLOOR: float = 0.3
"""Sub-score threshold below which the rationale is considered cosmetically
deficient. Conservative default; tune per deployment.
"""


# ── RuleSet ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RuleSet:
    """A collection of rules evaluated together against a (q, r, ctx) triple.

    Use :func:`groundlens_banking_rules` for the current canonical
    five-category ruleset, :func:`banking_rules` for the legacy three-category
    ruleset, or construct your own by passing a sequence of
    :class:`ChecklistRule` along with the list of sub-score categories the
    rules contribute to.

    Attributes:
        name: Identifier (e.g. ``"groundlens_banking_v1"``). Surfaced in audit logs.
        rules: The rules to evaluate.
        sub_scores: Ordered tuple of sub-score category names this ruleset
            produces. Rules whose ``sub_score`` field is not in this tuple are
            ignored at aggregation time (their evidence is still recorded in
            :attr:`RuleSetResult.rule_results`). Default
            ``("spec", "expl", "bshift")`` preserves legacy behavior.
        quality_floor: Default flag-predicate threshold below which a sub-score
            triggers the audit-deficiency flag. Applied to ``spec`` and
            ``expl`` only when :attr:`flag_predicate` is ``None``.
        flag_predicate: Optional pure function ``dict[str, float] -> bool`` that
            decides whether the aggregated result is flagged. When ``None``,
            the default legacy predicate is used: flagged iff
            ``spec < quality_floor or expl < quality_floor``.
    """

    name: str
    rules: tuple[ChecklistRule, ...]
    sub_scores: tuple[str, ...] = ("spec", "expl", "bshift")
    quality_floor: float = _DEFAULT_QUALITY_FLOOR
    flag_predicate: Callable[[dict[str, float]], bool] | None = None

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
        weights_by_sub: dict[str, float] = dict.fromkeys(self.sub_scores, 0.0)

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

        sub_scores: dict[str, float] = {
            name: round(min(1.0, weights_by_sub[name]), 4) for name in self.sub_scores
        }

        product = 1.0
        for value in sub_scores.values():
            product *= value
        n = len(sub_scores)
        quality = round(product ** (1.0 / n), 4) if product > 0 and n > 0 else 0.0

        if self.flag_predicate is not None:
            flagged = bool(self.flag_predicate(sub_scores))
        else:
            # Legacy default: flagged iff spec or expl below quality_floor.
            flagged = (sub_scores.get("spec", 0.0) < self.quality_floor) or (
                sub_scores.get("expl", 0.0) < self.quality_floor
            )

        audit = _format_audit_explanation(
            ruleset_name=self.name,
            sub_scores=sub_scores,
            quality=quality,
            flagged=flagged,
            quality_floor=self.quality_floor,
            results=results,
        )

        return RuleSetResult(
            sub_scores=sub_scores,
            quality=quality,
            flagged=flagged,
            rule_results=tuple(results),
            audit_explanation=audit,
        )


# ── Audit explanation formatter ─────────────────────────────────────────────


def _format_audit_explanation(
    *,
    ruleset_name: str,
    sub_scores: dict[str, float],
    quality: float,
    flagged: bool,
    quality_floor: float,
    results: Sequence[RuleResult],
) -> str:
    """Render a multi-line audit explanation suitable for log inclusion."""
    lines: list[str] = []
    lines.append(f"Ruleset: {ruleset_name}")
    sub_score_str = ", ".join(f"{name}={value:.3f}" for name, value in sub_scores.items())
    lines.append(f"Sub-scores: {sub_score_str} (quality={quality:.3f})")
    verdict = "FLAGGED" if flagged else "PASS"
    lines.append(f"Verdict: {verdict} (flag threshold={quality_floor})")

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
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response cite a regulatory flag present in the case metadata?"""
    flags_in_case: list[str] = list(metadata.get("flags_present", _BANKING_FLAGS))
    explanation = "Mentions a regulatory flag relevant to the case"
    ev = _matches_any(response, flags_in_case)
    return RuleEvidence(matched=ev.matched, span=ev.span, explanation=explanation)


def _check_risk_reference(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response reference a risk score or risk concept?"""
    ev = _matches_any(response, ["risk score", "risk level", "risk indicator", "risk"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="References risk score or risk concept"
    )


def _check_numeric_value(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response include a numeric value (case parameter or threshold)?"""
    ev = _matches_regex(response, _NUMERIC_RE)
    return RuleEvidence(matched=ev.matched, span=ev.span, explanation="Includes a numeric value")


def _check_gate_name(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response name a specific gate or threshold rule?"""
    ev = _matches_regex(response, _GATE_NAME_RE)
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Names a gate or threshold by identifier"
    )


def _check_information_gap(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response identify a missing-information gap?"""
    ev = _matches_any(
        response,
        ["completeness", "missing", "incomplete", "information gap", "documentation"],
    )
    return RuleEvidence(matched=ev.matched, span=ev.span, explanation="Names an information gap")


def _check_case_specific_detail(
    question: str,
    response: str,
    context: str | None,
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
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response provide substantive length (> 30 tokens)?"""
    matched = len(response.split()) > 30
    return RuleEvidence(matched=matched, span="", explanation="Substantive length (> 30 tokens)")


def _check_specificity_language(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response use specificity-marking language?"""
    ev = _matches_any(response, ["specifically", "in particular"])
    return RuleEvidence(
        matched=ev.matched,
        span=ev.span,
        explanation="Uses specificity-marking language",
    )


def _check_conditional_structure(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response use conditional structure (if / because / cannot)?"""
    ev = _matches_any(response, ["if ", "because", "cannot"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Uses conditional or causal structure"
    )


def _check_pending_action(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response name a pending action?"""
    ev = _matches_any(response, ["pending", "awaiting"])
    return RuleEvidence(matched=ev.matched, span=ev.span, explanation="Names a pending action")


def _check_causal_connective(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response use an explicit causal connective?"""
    ev = _matches_any(response, ["due to", "consequently", "therefore"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Uses an explicit causal connective"
    )


def _check_epistemic_limit(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response state an epistemic limitation?"""
    ev = _matches_any(response, ["cannot determine", "insufficient", "unable to"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="States an epistemic limitation"
    )


def _check_domain_reference(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response reference a domain concept (compliance / regulatory)?"""
    ev = _matches_any(response, ["compliance", "regulatory", "policy", "flag"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="References a domain concept"
    )


def _check_modal_verb(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response use a modal verb (would/should/need)?"""
    ev = _matches_any(response, ["would", "should", "need"])
    return RuleEvidence(matched=ev.matched, span=ev.span, explanation="Uses a modal verb")


def _check_minimum_length(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response meet minimum length (> 20 tokens)?"""
    matched = len(response.split()) > 20
    return RuleEvidence(matched=matched, span="", explanation="Minimum length (> 20 tokens)")


def _check_temporal_ordering(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response include temporal ordering (before / prior to / until)?"""
    ev = _matches_any(response, ["before", "prior to", "until"])
    return RuleEvidence(matched=ev.matched, span=ev.span, explanation="Includes temporal ordering")


def _check_conditional_approval(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
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
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response request additional information?"""
    ev = _matches_any(response, ["additional information", "further documentation", "more data"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Requests additional information"
    )


def _check_risk_reduction(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response propose risk-reduction language?"""
    ev = _matches_any(response, ["risk reduction", "mitigate", "reduce risk"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Proposes risk-reduction language"
    )


def _check_alternative_framing(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response offer an alternative framing?"""
    ev = _matches_any(response, ["otherwise", "alternatively"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="Offers an alternative framing"
    )


def _check_threshold_reference(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response reference a standard / threshold / criterion?"""
    ev = _matches_any(response, ["standard", "threshold", "criteria"])
    return RuleEvidence(
        matched=ev.matched, span=ev.span, explanation="References a threshold or criterion"
    )


def _check_resolution_length(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
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
        ChecklistRule("spec.info_gap", "information gap", 0.15, "spec", _check_information_gap),
        ChecklistRule(
            "spec.case_detail", "case-specific detail", 0.10, "spec", _check_case_specific_detail
        ),
        ChecklistRule(
            "spec.length", "substantive length", 0.10, "spec", _check_substantive_length
        ),
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
        ChecklistRule("expl.causal", "causal connective", 0.15, "expl", _check_causal_connective),
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


# ─────────────────────────────────────────────────────────────────────────────
# groundlens_banking_rules — current canonical ruleset.
#
# 20 rules organized into 5 emergent sub-scores: groundedness, completeness,
# calibration, traceability, robustness. Each rule carries a `citation` field
# pointing to its academic / industrial / regulatory provenance.
#
# The skeleton and the rules are derived empirically by triangulating five
# independent research tracks (peer-reviewed NLP, tier-1 banks, banking
# regulators, cross-industry frameworks, financial NLP benchmarks). The
# methodology and full per-rule provenance are documented in the companion
# paper "Defendable Rules for LLM Rationale Evaluation in Banking Governance:
# A Multi-Source Provenance Framework" (Marin, 2026).
# ─────────────────────────────────────────────────────────────────────────────


_SOURCE_SPAN_RE = re.compile(
    r"\bp\.\s?\d+|\bpage\s+\d+|\bsection\s+\d+|§\s?\d+|\bparagraph\s+\d+|\bclause\s+\d+",
    re.IGNORECASE,
)
"""Matches verbatim source-span references: page X, section X, §X, paragraph X."""

_CONFIDENCE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s?%|\b(?:confidence|probability|likelihood)\s+(?:of\s+)?\d+",
    re.IGNORECASE,
)
"""Matches numeric confidence expressions: '75%', 'confidence of 0.8', etc."""


def _check_grounded_in_context(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response stay grounded in the provided context?

    Deterministic proxy for RAGAs/ARES Faithfulness: compute the fraction of
    response content-word types that also appear in the context. When no
    context is supplied, the rule abstains (matched=True) because there is
    nothing to verify against.
    """
    if context is None or not context.strip():
        return RuleEvidence(
            matched=True, span="", explanation="No context provided — rule abstains"
        )
    resp_lower = response.lower()
    ctx_lower = context.lower()
    resp_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", resp_lower))
    if not resp_words:
        return RuleEvidence(matched=True, span="", explanation="Response has no content words")
    ctx_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", ctx_lower))
    overlap = len(resp_words & ctx_words) / len(resp_words)
    threshold = 0.4
    if overlap >= threshold:
        return RuleEvidence(
            matched=True,
            span=f"overlap={overlap:.2f}",
            explanation="Response content overlaps the context",
        )
    return RuleEvidence(
        matched=False,
        span=f"overlap={overlap:.2f}",
        explanation=(f"Response content overlap {overlap:.2f} below threshold {threshold}"),
    )


def _check_atomic_decomposable(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Can the rationale be decomposed into at least two distinct claim units?"""
    sentence_terminators = re.findall(r"[.!?]", response)
    matched = len(sentence_terminators) >= 2
    return RuleEvidence(
        matched=matched,
        span=f"sentences={len(sentence_terminators)}",
        explanation="Rationale contains at least two sentence-level claims",
    )


def _check_no_unsupported_extensions(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the response avoid introducing numbers absent from the context?

    Deterministic proxy for extrinsic-hallucination resistance: every numeric
    token in the response must also occur in the context. When no context is
    supplied, the rule abstains.
    """
    if context is None or not context.strip():
        return RuleEvidence(
            matched=True, span="", explanation="No context provided — rule abstains"
        )
    resp_nums = set(re.findall(r"\b\d+(?:\.\d+)?\b", response))
    if not resp_nums:
        return RuleEvidence(matched=True, span="", explanation="No numeric claims to verify")
    ctx_nums = set(re.findall(r"\b\d+(?:\.\d+)?\b", context))
    introduced = resp_nums - ctx_nums
    if not introduced:
        return RuleEvidence(
            matched=True, span="", explanation="All response numbers appear in context"
        )
    return RuleEvidence(
        matched=False,
        span=f"introduced={sorted(introduced)[:3]}",
        explanation=f"Response introduced {len(introduced)} numeric claim(s) absent from context",
    )


def _check_counterfactual_robustness(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Has the rationale been screened against wrong-retrieval scenarios?

    System-level check via metadata: matches when ``metadata["context_quality_validated"]``
    is truthy, indicating that the deploying pipeline ran the response through
    a counterfactual-robustness check (e.g. RGB-style adversarial retrieval).
    Defaults to True when the flag is absent (assume external validation).
    """
    validated = bool(metadata.get("context_quality_validated", True))
    return RuleEvidence(
        matched=validated,
        span="metadata.context_quality_validated",
        explanation="Pipeline reports counterfactual-robustness screening passed",
    )


def _check_addresses_all_parts(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the response length scale with the question's number of sub-questions?"""
    sub_questions = max(1, question.count("?"))
    min_tokens = 25 * sub_questions
    n_tokens = len(response.split())
    matched = n_tokens >= min_tokens
    return RuleEvidence(
        matched=matched,
        span=f"tokens={n_tokens}, required={min_tokens}",
        explanation=f"Response length covers {sub_questions} sub-question(s)",
    )


_GOVERNANCE_DIMENSIONS: tuple[str, ...] = (
    "borrower",
    "transaction",
    "security",
    "collateral",
    "exposure",
    "limit",
    "jurisdiction",
    "policy",
    "counterparty",
    "customer",
    "regulator",
    "compliance",
    "risk",
    "control",
)


def _check_governance_dimensions(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the rationale reference at least two distinct governance dimensions?"""
    resp_lower = response.lower()
    hits = [dim for dim in _GOVERNANCE_DIMENSIONS if dim in resp_lower]
    matched = len(hits) >= 2
    return RuleEvidence(
        matched=matched,
        span=", ".join(hits[:3]) if hits else "",
        explanation="Rationale references multiple governance dimensions",
    )


def _check_information_integration(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the rationale integrate multiple sources via integration connectives?"""
    ev = _matches_any(
        response,
        ["combined", "together", "across", "between", "both ", "in addition", "moreover"],
    )
    return RuleEvidence(
        matched=ev.matched,
        span=ev.span,
        explanation="Rationale uses multi-source integration language",
    )


def _check_abstains_when_insufficient(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the rationale explicitly abstain when evidence is insufficient?"""
    ev = _matches_any(
        response,
        [
            "insufficient information",
            "cannot determine",
            "unable to confirm",
            "not enough evidence",
            "i don't know",
            "cannot be answered",
            "no relevant",
            "missing data",
        ],
    )
    return RuleEvidence(
        matched=ev.matched,
        span=ev.span,
        explanation="Rationale explicitly abstains on insufficient evidence",
    )


def _check_explicit_hedging(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the rationale use explicit hedging language?"""
    ev = _matches_any(
        response,
        [
            " may ",
            " might ",
            "suggests",
            "appears",
            "appears to",
            "likely",
            "probably",
            "possibly",
            "seems to",
            "could be",
        ],
    )
    return RuleEvidence(
        matched=ev.matched,
        span=ev.span.strip(),
        explanation="Rationale uses hedging language to express uncertainty",
    )


def _check_confidence_score(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the rationale carry a numeric confidence / probability score?"""
    ev = _matches_regex(response, _CONFIDENCE_RE)
    return RuleEvidence(
        matched=ev.matched,
        span=ev.span,
        explanation="Rationale includes a numeric confidence or probability",
    )


def _check_self_consistency(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Did the production pipeline screen the response for self-consistency?

    System-level check via metadata: matches when ``metadata["consistency_check_passed"]``
    is truthy. Defaults to True when absent (assume external validation).
    """
    validated = bool(metadata.get("consistency_check_passed", True))
    return RuleEvidence(
        matched=validated,
        span="metadata.consistency_check_passed",
        explanation="Pipeline reports self-consistency screening passed",
    )


def _check_specific_source_span(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the rationale cite a specific source span (page, section, paragraph, clause)?"""
    ev = _matches_regex(response, _SOURCE_SPAN_RE)
    return RuleEvidence(
        matched=ev.matched,
        span=ev.span,
        explanation="Rationale cites a specific source span",
    )


def _check_falsifiable_actionable(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the rationale make at least one specific testable claim?

    Approximated by the conjunction of: a numeric value present AND a causal
    connective present. Such a rationale couples a concrete claim to a
    causal mechanism, which is what makes the claim testable.
    """
    has_number = bool(_NUMERIC_RE.search(response))
    causal_ev = _matches_any(response, ["because", "due to", "therefore", "consequently"])
    matched = has_number and causal_ev.matched
    return RuleEvidence(
        matched=matched,
        span=causal_ev.span if matched else "",
        explanation="Rationale couples a numeric claim with a causal mechanism",
    )


def _check_audit_logged(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Has the rationale been persisted to the audit log?

    System-level check via metadata: matches when ``metadata["audit_logged"]``
    is truthy. Defaults to True when absent (assume external audit pipeline,
    e.g. ``groundlens.audit.AuditLog``).
    """
    logged = bool(metadata.get("audit_logged", True))
    return RuleEvidence(
        matched=logged,
        span="metadata.audit_logged",
        explanation="Pipeline reports rationale persisted to audit log",
    )


def _check_independent_validation(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the rationale or its pipeline reference independent validation?"""
    text_ev = _matches_any(
        response,
        [
            "validated by",
            "reviewed by",
            "second opinion",
            "checked by",
            "verified by",
            "independent review",
            "independent validation",
            "effective challenge",
        ],
    )
    metadata_validated = bool(metadata.get("independent_review_completed", False))
    matched = text_ev.matched or metadata_validated
    span = text_ev.span if text_ev.matched else "metadata.independent_review_completed"
    return RuleEvidence(
        matched=matched,
        span=span if matched else "",
        explanation="Rationale or pipeline references independent validation",
    )


def _check_prompt_injection_robust(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Has the rationale been screened for prompt-injection / distractor robustness?

    System-level check via metadata: matches when ``metadata["injection_test_passed"]``
    is truthy. Defaults to True when absent (assume external validation).
    """
    validated = bool(metadata.get("injection_test_passed", True))
    return RuleEvidence(
        matched=validated,
        span="metadata.injection_test_passed",
        explanation="Pipeline reports prompt-injection robustness screening passed",
    )


def _check_cross_source_conflict(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
) -> RuleEvidence:
    """Does the rationale identify cross-source conflicts when they exist?"""
    ev = _matches_any(
        response,
        [
            "conflict",
            "conflicting",
            "disagrees",
            "disagreement",
            "inconsistent",
            "however",
            "but the",
            "discrepancy",
            "mismatch",
        ],
    )
    return RuleEvidence(
        matched=ev.matched,
        span=ev.span,
        explanation="Rationale acknowledges a cross-source conflict",
    )


def _groundlens_banking_flag_predicate(sub_scores: dict[str, float]) -> bool:
    """Default flag predicate for the GroundLens banking ruleset.

    Flagged when any of the three regulator-non-negotiable sub-scores falls
    below its rule-set threshold:

    - ``groundedness < 0.5`` — claim-to-source linkage is the EU AI Act Art. 13
      and NIST 600-1 confabulation requirement.
    - ``calibration < 0.3`` — uncertainty expression is required by SR 26-2 §V
      and EU AI Act Art. 13(3)(b)(ii).
    - ``traceability < 0.4`` — citation and audit-trail are required by
      EU AI Act Art. 12 and SR 26-2 §VI.
    """
    return (
        sub_scores.get("groundedness", 0.0) < 0.5
        or sub_scores.get("calibration", 0.0) < 0.3
        or sub_scores.get("traceability", 0.0) < 0.4
    )


def groundlens_banking_rules(quality_floor: float = _DEFAULT_QUALITY_FLOOR) -> RuleSet:
    """Canonical rule set for LLM rationale evaluation in banking governance.

    Returns the 20-rule reference set whose provenance is triangulated across
    five independent research tracks: peer-reviewed NLP literature, tier-1
    bank public reports, banking regulator whitepapers, cross-industry
    frameworks, and financial-domain NLP benchmarks. The rules are organized
    into five empirically-emergent sub-score categories:

    - **groundedness** (5 rules): claims linked to and supported by source.
    - **completeness** (3 rules): coverage of the governance question.
    - **calibration** (4 rules): uncertainty expression and abstention.
    - **traceability** (5 rules): citation, audit trail, validation references.
    - **robustness** (3 rules): resistance to noise, conflict, injection.

    Each rule carries a ``citation`` field pointing to at least one of its
    academic, industrial, or regulatory provenance sources. The companion
    paper (Marin, 2026) documents the full per-rule provenance.

    The default flag predicate :func:`_groundlens_banking_flag_predicate`
    triggers when any regulator-non-negotiable sub-score falls below its
    threshold (groundedness < 0.5, calibration < 0.3, or traceability < 0.4).

    Args:
        quality_floor: Legacy floor exposed for users who want a uniform
            threshold across sub-scores. Not used by the default flag
            predicate; kept for compatibility with the legacy ``banking_rules()``
            signature so deployers can A/B both rulesets with one parameter.

    Returns:
        A :class:`RuleSet` named ``"groundlens_banking_v1"`` with five
        sub-scores and 20 rules.
    """
    rules: tuple[ChecklistRule, ...] = (
        # ── Groundedness (5 rules) ──────────────────────────────────────────
        ChecklistRule(
            id="grnd.claim_supported_by_context",
            description="every claim inferable from context",
            weight=0.25,
            sub_score="groundedness",
            check=_check_grounded_in_context,
            citation="RAGAs (Es et al., EACL 2024) §3; NIST AI 600-1 (2024) §2.2 Confabulation",
        ),
        ChecklistRule(
            id="grnd.atomic_decomposition",
            description="rationale decomposable into atomic claims",
            weight=0.20,
            sub_score="groundedness",
            check=_check_atomic_decomposable,
            citation="FactScore (Min et al., EMNLP 2023) §3; RAGAs (Es et al., EACL 2024) §3",
        ),
        ChecklistRule(
            id="grnd.no_unsupported_extensions",
            description="no claims beyond what context supports",
            weight=0.20,
            sub_score="groundedness",
            check=_check_no_unsupported_extensions,
            citation=(
                "HaluEval (Li et al., EMNLP 2023); Ji et al. ACM CSUR 2023; NIST AI 600-1 (2024)"
            ),
        ),
        ChecklistRule(
            id="grnd.regulatory_flag",
            description="names a specific regulatory flag or policy clause",
            weight=0.20,
            sub_score="groundedness",
            check=_check_regulatory_flag,
            citation="REV (Chen et al., ACL 2023); SR 26-2 (Fed/OCC/FDIC 2026) §VI Documentation",
        ),
        ChecklistRule(
            id="grnd.counterfactual_robust",
            description="screened against wrong-retrieval scenarios",
            weight=0.15,
            sub_score="groundedness",
            check=_check_counterfactual_robustness,
            citation="RGB (Chen et al., AAAI 2024); EU AI Act 2024/1689 Art. 15(4)",
        ),
        # ── Completeness (3 rules) ──────────────────────────────────────────
        ChecklistRule(
            id="comp.addresses_all_parts",
            description="response length scales with question parts",
            weight=0.40,
            sub_score="completeness",
            check=_check_addresses_all_parts,
            citation="RAGAs (Es et al., EACL 2024) §3; EU AI Act 2024/1689 Art. 13(2)",
        ),
        ChecklistRule(
            id="comp.governance_dimensions",
            description="references multiple governance dimensions",
            weight=0.35,
            sub_score="completeness",
            check=_check_governance_dimensions,
            citation="EBA GL/2020/06 §4.3.3; SR 26-2 (Fed/OCC/FDIC 2026) §IV Model Development",
        ),
        ChecklistRule(
            id="comp.information_integration",
            description="integrates multiple sources",
            weight=0.25,
            sub_score="completeness",
            check=_check_information_integration,
            citation="RGB (Chen et al., AAAI 2024); TRUE (Honovich et al., NAACL 2022)",
        ),
        # ── Calibration (4 rules) ───────────────────────────────────────────
        ChecklistRule(
            id="cal.abstains_when_insufficient",
            description="explicitly abstains when evidence is insufficient",
            weight=0.35,
            sub_score="calibration",
            check=_check_abstains_when_insufficient,
            citation=(
                "RAGAs (Es et al., EACL 2024) §3; FinanceBench (Islam et al., 2023); "
                "SR 26-2 §V Model Validation"
            ),
        ),
        ChecklistRule(
            id="cal.explicit_hedging",
            description="uses hedging language for uncertain claims",
            weight=0.30,
            sub_score="calibration",
            check=_check_explicit_hedging,
            citation=(
                "TruthfulQA (Lin et al., ACL 2022); Hyland (1998) hedging taxonomy; "
                "SR 26-2 §IV Model Use"
            ),
        ),
        ChecklistRule(
            id="cal.confidence_score",
            description="includes a numeric confidence or probability",
            weight=0.20,
            sub_score="calibration",
            check=_check_confidence_score,
            citation="G-Eval (Liu et al., EMNLP 2023); EU AI Act Art. 13(3)(b)(ii)",
        ),
        ChecklistRule(
            id="cal.self_consistency",
            description="pipeline screened for self-consistency",
            weight=0.15,
            sub_score="calibration",
            check=_check_self_consistency,
            citation="SelfCheckGPT (Manakul et al., EMNLP 2023); Morgan Stanley + OpenAI (2024)",
        ),
        # ── Traceability (5 rules) ──────────────────────────────────────────
        ChecklistRule(
            id="trace.specific_source_span",
            description="cites a specific page / section / paragraph",
            weight=0.25,
            sub_score="traceability",
            check=_check_specific_source_span,
            citation=(
                "e-SNLI (Camburu et al., NeurIPS 2018); EU AI Act Art. 13(3)(b)(iv); "
                "FinanceBench (Islam et al., 2023)"
            ),
        ),
        ChecklistRule(
            id="trace.natural_language_rationale",
            description="provides a substantive natural-language rationale",
            weight=0.20,
            sub_score="traceability",
            check=_check_substantive_length,
            citation=(
                "e-SNLI (Camburu et al., NeurIPS 2018); EU AI Act Art. 13(3)(b)(iv); "
                "PRA SS1/23 Principle 3"
            ),
        ),
        ChecklistRule(
            id="trace.falsifiable_actionable",
            description="couples numeric claim with causal mechanism",
            weight=0.20,
            sub_score="traceability",
            check=_check_falsifiable_actionable,
            citation="REV (Chen et al., ACL 2023); SR 26-2 §V Conceptual Soundness",
        ),
        ChecklistRule(
            id="trace.numeric_value",
            description="includes a numeric value or metric",
            weight=0.15,
            sub_score="traceability",
            check=_check_numeric_value,
            citation=(
                "FinQA (Chen et al., EMNLP 2021); EU AI Act Art. 13(3)(b)(ii); "
                "SR 26-2 §V Outcomes Analysis"
            ),
        ),
        ChecklistRule(
            id="trace.audit_logged",
            description="rationale persisted to audit log",
            weight=0.20,
            sub_score="traceability",
            check=_check_audit_logged,
            citation=(
                "EU AI Act Art. 12 Record-Keeping; SR 26-2 §VI Documentation; "
                "ISO/IEC 42001:2023 §8.2"
            ),
        ),
        # ── Robustness (3 rules) ────────────────────────────────────────────
        ChecklistRule(
            id="rob.independent_validation",
            description="references independent validation / effective challenge",
            weight=0.40,
            sub_score="robustness",
            check=_check_independent_validation,
            citation=(
                "SR 26-2 §III Effective Challenge; PRA SS1/23 Principle 4; "
                "ECB Guide to Internal Models §9.3 ¶43(a)"
            ),
        ),
        ChecklistRule(
            id="rob.prompt_injection_robust",
            description="pipeline screened for prompt-injection robustness",
            weight=0.35,
            sub_score="robustness",
            check=_check_prompt_injection_robust,
            citation="RGB (Chen et al., AAAI 2024); EU AI Act Art. 15; MAS MindForge (2024)",
        ),
        ChecklistRule(
            id="rob.cross_source_conflict",
            description="acknowledges cross-source conflicts",
            weight=0.25,
            sub_score="robustness",
            check=_check_cross_source_conflict,
            citation=(
                "ConflictBank (Su et al., 2024); EU AI Act Art. 15(4); RGB (Chen et al., 2024)"
            ),
        ),
    )

    return RuleSet(
        name="groundlens_banking_v1",
        rules=rules,
        sub_scores=("groundedness", "completeness", "calibration", "traceability", "robustness"),
        quality_floor=quality_floor,
        flag_predicate=_groundlens_banking_flag_predicate,
    )


# ─────────────────────────────────────────────────────────────────────────────
# decision_rationale_rules — canonical name for the 20-rule banking set.
#
# Phase 2 of the rule-set API refactor (ADR 0001): the archetype goes in the
# function name; the deployment dimensions go in keyword arguments.
# ─────────────────────────────────────────────────────────────────────────────


_VALID_DECISION_RATIONALE_DOMAINS: tuple[str, ...] = ("finance",)
"""Domains the decision-rationale archetype currently ships rules for.

Legal, healthcare, and insurance verticalizations are on the roadmap and will
be added here when a real deployment requests them. Until then, calling
``decision_rationale_rules(domain="legal")`` raises ``ValueError`` rather than
silently returning the finance-calibrated set.
"""

_REGULATION_CITATION_KEYS: dict[str, tuple[str, ...]] = {
    "eu_ai_act": ("EU AI Act", "2024/1689", "Art. 12", "Art. 13", "Art. 15"),
    "sr_26_2": ("SR 26-2",),
    "sr_11_7": ("SR 11-7",),
    "nist_ai_600_1": ("NIST AI 600-1", "NIST AI 600", "NIST 600-1"),
    "nist_ai_rmf": ("NIST AI RMF",),
    "iso_42001": ("ISO/IEC 42001", "ISO 42001"),
    "ecb_internal_models": ("ECB Guide to Internal Models",),
    "eba_gl_2020_06": ("EBA GL/2020/06",),
    "pra_ss1_23": ("PRA SS1/23",),
    "hipaa": ("HIPAA",),
    "gdpr": ("GDPR",),
}
"""Substring keys used to filter ``audit_explanation`` lines when
``regulations=`` is set on ``decision_rationale_rules``.

The filter is a substring match on each rule's ``citation`` field. It does not
add or remove rules; it only suppresses citation lines that do not mention any
of the requested regulations from the rendered audit text. Rules whose
citation does not mention any regulation (academic-only citations) are kept
unconditionally.
"""


def decision_rationale_rules(
    domain: str = "finance",
    regulations: tuple[str, ...] = (),
    quality_floor: float = _DEFAULT_QUALITY_FLOOR,
) -> RuleSet:
    """Rule set for decision-rationale agents (credit / AML / KYC / sanctions).

    Canonical factory for the 20-rule, 5-sub-score decision-rationale
    rule set. Replaces :func:`groundlens_banking_rules` under the
    archetype-as-function naming convention introduced in ADR 0001
    (release 2026.6.13).

    Args:
        domain: Deployment domain. Currently only ``"finance"`` (default)
            is supported; calling with any other value raises
            ``ValueError`` so the caller knows the verticalization is not
            yet shipped. Insurance, healthcare, and legal vertical
            decision-rationale sets are on the roadmap.
        regulations: Optional tuple of regulation keys. When non-empty,
            ``audit_explanation`` lines whose rule citation does not
            mention any of the requested regulations are suppressed from
            the rendered audit text. Does not add or remove rules. Valid
            keys include: ``"eu_ai_act"``, ``"sr_26_2"``, ``"sr_11_7"``,
            ``"nist_ai_600_1"``, ``"nist_ai_rmf"``, ``"iso_42001"``,
            ``"ecb_internal_models"``, ``"eba_gl_2020_06"``,
            ``"pra_ss1_23"``, ``"hipaa"``, ``"gdpr"``.

            *Implementation note (2026.6.13):* the kwarg is accepted and
            validated, but provenance-filtered rendering of
            ``audit_explanation`` will land in a follow-up release. For
            now the audit text is unmodified; the rule set is returned
            unchanged. A ``UserWarning`` is emitted when the kwarg is
            non-empty so the caller is aware the filter is not yet active.
        quality_floor: Threshold below which a sub-score triggers the
            cosmetic-deadlock flag. Kept for compatibility with the
            legacy ``banking_rules()`` signature.

    Returns:
        A :class:`RuleSet` named ``"decision_rationale_v1_finance"`` with
        five sub-scores and 20 rules. The rules and weights are identical
        to those of :func:`groundlens_banking_rules`; only the rule-set
        name is updated.

    Raises:
        ValueError: If ``domain`` is not in
            :data:`_VALID_DECISION_RATIONALE_DOMAINS`.

    Example::

        from groundlens import decision_rationale_rules

        rs = decision_rationale_rules(
            domain="finance",
            regulations=("eu_ai_act", "sr_26_2"),
        )
        result = rs.evaluate(question=q, response=r, context=ctx)
    """
    if domain not in _VALID_DECISION_RATIONALE_DOMAINS:
        msg = (
            f"decision_rationale_rules(domain={domain!r}) — supported domains "
            f"are {_VALID_DECISION_RATIONALE_DOMAINS}. Other verticalizations "
            "are on the roadmap; open an issue at "
            "https://github.com/groundlens-dev/groundlens/issues to request "
            "one."
        )
        raise ValueError(msg)

    unknown = tuple(r for r in regulations if r not in _REGULATION_CITATION_KEYS)
    if unknown:
        msg = (
            f"decision_rationale_rules(regulations={regulations!r}) — unknown "
            f"keys {unknown}. Known keys: "
            f"{tuple(_REGULATION_CITATION_KEYS.keys())}."
        )
        raise ValueError(msg)
    if regulations:
        warnings.warn(
            "decision_rationale_rules(regulations=...) is accepted but the "
            "provenance-filtered audit_explanation rendering is not yet "
            "active (slated for a follow-up release). The returned RuleSet "
            "is unchanged.",
            UserWarning,
            stacklevel=2,
        )

    base = groundlens_banking_rules(quality_floor=quality_floor)
    # Replace the legacy name with the archetype-aware canonical name.
    object.__setattr__(base, "name", f"decision_rationale_v1_{domain}")
    return base


__all__ = [
    "ChecklistRule",
    "RuleEvidence",
    "RuleResult",
    "RuleSet",
    "RuleSetResult",
    "banking_rules",
    "decision_rationale_rules",
    "groundlens_banking_rules",
]
