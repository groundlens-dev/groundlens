"""Routing agent triage — rules for intent classification agents.

Routing agents classify a user query into one of N candidate operations
(in production deployments, N can exceed 150) and decide whether to
clarify or fall back. Their failure modes are distinct from those of
RAG agents: mis-classification, over-use of fallback, under-use of
clarification on ambiguous queries, and drift between the predicted
intent and the actual content of the query.

The rule set below evaluates a routing decision across four sub-scores:

- ``intent_clarity`` — is the query interpretable as a single intent?
- ``classification_confidence`` — is the top-1 decision well-anchored?
- ``fallback_appropriateness`` — if fallback fired, was it the right call?
- ``disambiguation_quality`` — if clarification fired, was it specific?

Expected metadata keys (all optional — rules abstain when missing):

- ``predicted_intent`` (str): the routing agent's top-1 intent label.
- ``top1_score`` (float in [0, 1]): the confidence of the top-1 prediction.
- ``margin`` (float): the gap between top-1 and top-2 scores.
- ``allowed_intents`` (Iterable[str]): the closed set of intents the
  routing agent is configured to predict.
- ``fallback_fired`` (bool): whether the agent returned a fallback response.
- ``query_in_scope`` (bool): whether the query is in the operation taxonomy.
- ``clarify_fired`` (bool): whether the agent asked a clarification.
- ``candidate_intents`` (Iterable[str]): the two-or-more intents the
  clarify question is disambiguating between.

References:
    Sarikaya, R., Hinton, G. E., & Deoras, A. (2014). Application of
        deep belief networks for natural language understanding.
        IEEE/ACM TASLP, 22(4), 778-784.

    Guo, C., Pleiss, G., Sun, Y., & Weinberger, K. Q. (2017). On
        calibration of modern neural networks. ICML 2017.

    Rao, S., & Daumé III, H. (2018). Learning to ask good questions:
        Ranking clarification questions using neural expected value of
        perfect information. ACL 2018.
"""

from __future__ import annotations

import re
from typing import Any

from groundlens.rules import ChecklistRule, RuleEvidence, RuleSet

# ── Check functions ─────────────────────────────────────────────────────────


_MULTI_INTENT_CONJUNCTIONS = (
    " and also ",
    " and then ",
    " plus ",
    "; also ",
    " además de ",
    " y también ",
)


def check_single_intent_signal(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Query carries a single intent, not multiple chained operations.

    A routing decision over a multi-intent query is structurally ambiguous —
    the agent should split or clarify before classifying.
    """
    q = question.lower()
    hits = [marker for marker in _MULTI_INTENT_CONJUNCTIONS if marker in q]
    if hits:
        return RuleEvidence(
            matched=False,
            span=hits[0].strip(),
            explanation="query chains multiple intents — should split or clarify",
        )
    return RuleEvidence(
        matched=True,
        span="",
        explanation="query reads as a single intent",
    )


_PRONOUN_LEAD = re.compile(r"^\s*(it|that|this|they|them|eso|esto|ello)\b", re.IGNORECASE)


def check_no_ambiguous_pronoun_lead(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Query does not start with a bare pronoun without antecedent.

    Pronoun-led queries depend on prior turns. A single-turn routing
    decision cannot resolve the referent — clarify is the correct path.
    """
    match = _PRONOUN_LEAD.search(question)
    if match:
        return RuleEvidence(
            matched=False,
            span=match.group(0).strip(),
            explanation="query opens with bare pronoun — antecedent unresolved",
        )
    return RuleEvidence(
        matched=True,
        span="",
        explanation="query opens with a referential noun phrase",
    )


def check_intent_shares_query_tokens(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Predicted intent shares at least one content token with the query.

    Cheap concept-drift check. If the predicted intent label has no
    surface overlap with the query, the routing decision deserves a
    second look (or the intent taxonomy uses opaque IDs — in which case
    the rule should be customized to consult an ID-to-keyword map).
    """
    predicted = metadata.get("predicted_intent")
    if not predicted:
        return RuleEvidence(
            matched=True, span="", explanation="no predicted_intent in metadata — abstains"
        )
    intent_tokens = set(re.findall(r"[a-z]{4,}", str(predicted).lower()))
    query_tokens = set(re.findall(r"[a-z]{4,}", question.lower()))
    overlap = intent_tokens & query_tokens
    if overlap:
        return RuleEvidence(
            matched=True,
            span=", ".join(sorted(overlap)[:3]),
            explanation="predicted intent shares tokens with query",
        )
    return RuleEvidence(
        matched=False,
        span=str(predicted),
        explanation="predicted intent has no token overlap with query",
    )


def check_top1_confidence_above_threshold(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Top-1 routing confidence exceeds threshold (default 0.7).

    Calibrated classifiers should not return high-confidence labels on
    inputs they cannot resolve. A low top-1 score is a flag, not a
    veto: the agent should fall back or clarify, not silently route.
    """
    threshold = float(metadata.get("confidence_threshold", 0.7))
    score = metadata.get("top1_score")
    if score is None:
        return RuleEvidence(matched=True, span="", explanation="no top1_score — abstains")
    score_f = float(score)
    if score_f >= threshold:
        return RuleEvidence(
            matched=True,
            span=f"top1={score_f:.2f}>={threshold:.2f}",
            explanation="top-1 confidence above operational threshold",
        )
    return RuleEvidence(
        matched=False,
        span=f"top1={score_f:.2f}<{threshold:.2f}",
        explanation="top-1 confidence below operational threshold",
    )


def check_margin_to_runner_up(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Margin between top-1 and top-2 scores is at least 0.15.

    Tight margins indicate the routing decision is a coin-flip between
    two plausible intents. Production deployments should disambiguate
    via clarification on tight-margin cases.
    """
    margin_floor = float(metadata.get("margin_floor", 0.15))
    margin = metadata.get("margin")
    if margin is None:
        return RuleEvidence(matched=True, span="", explanation="no margin — abstains")
    margin_f = float(margin)
    if margin_f >= margin_floor:
        return RuleEvidence(
            matched=True,
            span=f"margin={margin_f:.2f}",
            explanation="margin to runner-up above floor",
        )
    return RuleEvidence(
        matched=False,
        span=f"margin={margin_f:.2f}<{margin_floor:.2f}",
        explanation="margin to runner-up below floor — clarify recommended",
    )


def check_intent_in_allowed_set(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Predicted intent belongs to the configured allowed set.

    Defensive check against open-vocabulary failures. If
    ``allowed_intents`` is not provided, the rule abstains.
    """
    predicted = metadata.get("predicted_intent")
    allowed = metadata.get("allowed_intents")
    if predicted is None or allowed is None:
        return RuleEvidence(matched=True, span="", explanation="no allowed_intents — abstains")
    if str(predicted) in {str(x) for x in allowed}:
        return RuleEvidence(
            matched=True,
            span=str(predicted),
            explanation="predicted intent in allowed set",
        )
    return RuleEvidence(
        matched=False,
        span=str(predicted),
        explanation="predicted intent not in allowed set",
    )


def check_fallback_when_out_of_scope(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """If fallback fired, the query is actually out of scope.

    Counterpart rule: fallback should not fire on in-scope queries. This
    catches the failure where the agent gives up on a query it could
    have routed correctly.
    """
    fallback = metadata.get("fallback_fired")
    if fallback is None or not fallback:
        return RuleEvidence(
            matched=True, span="", explanation="no fallback fired — rule does not apply"
        )
    in_scope = metadata.get("query_in_scope")
    if in_scope is None:
        return RuleEvidence(matched=True, span="", explanation="query_in_scope unknown — abstains")
    if not in_scope:
        return RuleEvidence(
            matched=True,
            span="fallback+oos",
            explanation="fallback appropriate — query is out of scope",
        )
    return RuleEvidence(
        matched=False,
        span="fallback+in-scope",
        explanation="fallback fired on in-scope query — false negative",
    )


def check_no_silent_fallback(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """If fallback fired, the response explains the limit rather than being empty.

    A silent fallback degrades UX and obscures the agent's reasoning
    from any downstream auditor.
    """
    fallback = metadata.get("fallback_fired")
    if not fallback:
        return RuleEvidence(
            matched=True, span="", explanation="no fallback fired — rule does not apply"
        )
    if len(response.strip()) >= 20:
        return RuleEvidence(
            matched=True,
            span=f"len={len(response.strip())}",
            explanation="fallback explains the limit to the user",
        )
    return RuleEvidence(
        matched=False,
        span=f"len={len(response.strip())}",
        explanation="fallback fired but response is empty or near-empty",
    )


_CLARIFY_QUESTION_MARKERS = ("?", "¿", " or ", " o ", "which ", "cuál ", "do you mean")


def check_clarify_when_ambiguous(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """If the margin is below floor and no fallback fired, response asks a clarification.

    The decision tree the rule audits: low margin + not OOS → clarify.
    Routing silently on low-margin cases is a known production failure mode.
    """
    margin = metadata.get("margin")
    margin_floor = float(metadata.get("margin_floor", 0.15))
    fallback = metadata.get("fallback_fired", False)
    if margin is None or fallback:
        return RuleEvidence(
            matched=True, span="", explanation="rule does not apply (no margin or fallback fired)"
        )
    if float(margin) >= margin_floor:
        return RuleEvidence(
            matched=True, span="", explanation="margin above floor — clarify not required"
        )
    r_lower = response.lower()
    is_question = any(marker in r_lower for marker in _CLARIFY_QUESTION_MARKERS)
    if is_question:
        return RuleEvidence(
            matched=True,
            span="clarify",
            explanation="low-margin case correctly answered with a clarification question",
        )
    return RuleEvidence(
        matched=False,
        span="silent route",
        explanation="low-margin case routed silently without clarification",
    )


def check_specific_clarify_question(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """If clarify fired, the question references the two candidate intents.

    A generic 'could you rephrase?' is less useful than 'do you mean X
    or Y?'. Specific clarifications are higher-quality.
    """
    clarify = metadata.get("clarify_fired")
    candidates = metadata.get("candidate_intents")
    if not clarify:
        return RuleEvidence(
            matched=True, span="", explanation="no clarify fired — rule does not apply"
        )
    if not candidates:
        return RuleEvidence(matched=True, span="", explanation="no candidate_intents — abstains")
    r_lower = response.lower()
    candidate_tokens: set[str] = set()
    for c in candidates:
        candidate_tokens.update(re.findall(r"[a-z]{4,}", str(c).lower()))
    hits = [t for t in candidate_tokens if t in r_lower]
    if len(hits) >= 2:
        return RuleEvidence(
            matched=True,
            span=", ".join(sorted(hits)[:3]),
            explanation="clarify question references at least two candidate intents",
        )
    return RuleEvidence(
        matched=False,
        span=", ".join(sorted(hits)) or "none",
        explanation="clarify question does not name competing intents specifically",
    )


# ── Flag predicate ──────────────────────────────────────────────────────────


def routing_flag_predicate(sub_scores: dict[str, float]) -> bool:
    """Flag when classification_confidence or fallback_appropriateness collapse.

    Routing agents that act on low-confidence decisions or that fall
    back inappropriately are operationally dangerous: they route real
    money or real-customer queries to the wrong pipeline. The flag
    triggers human review without aggregating across dimensions.
    """
    return (
        sub_scores.get("classification_confidence", 0.0) < 0.5
        or sub_scores.get("fallback_appropriateness", 0.0) < 0.5
        or sub_scores.get("intent_clarity", 0.0) < 0.3
    )


# ── The rule set ────────────────────────────────────────────────────────────


_VALID_ROUTING_DOMAINS: tuple[str, ...] = ("general", "finance", "healthcare", "legal")


def routing_rules(domain: str = "general") -> RuleSet:
    """Rule set for routing / intent classification agents.

    Returns a 10-rule set across 4 sub-scores: intent_clarity,
    classification_confidence, fallback_appropriateness,
    disambiguation_quality. Each rule carries a citation to its
    academic, industrial, or regulatory source.

    Args:
        domain: Deployment domain. Currently the routing rule set is
            domain-agnostic by design — the rules check structural
            properties of routing decisions (single intent, top-1 margin,
            fallback appropriateness, clarification quality) that hold
            across verticals. The kwarg is accepted for API symmetry with
            the other archetype factories and to leave a slot for
            domain-specific routing extensions in a future release.

            One of: ``"general"`` (default), ``"finance"``,
            ``"healthcare"``, ``"legal"``.

    Returns:
        A :class:`RuleSet` named ``"groundlens_routing_v1"``.

    Raises:
        ValueError: If ``domain`` is not in :data:`_VALID_ROUTING_DOMAINS`.

    Example::

        from groundlens.agents import routing_rules

        rs = routing_rules()
        result = rs.evaluate(
            question="transfer 500 to my brother and check my balance",
            response="I will transfer 500 EUR.",
            metadata={
                "predicted_intent": "transfer",
                "top1_score": 0.62,
                "margin": 0.08,
                "fallback_fired": False,
                "query_in_scope": True,
            },
        )
        assert result.flagged  # low confidence + multi-intent
    """
    if domain not in _VALID_ROUTING_DOMAINS:
        msg = f"routing_rules(domain={domain!r}) — supported domains are {_VALID_ROUTING_DOMAINS}."
        raise ValueError(msg)
    rules = (
        # intent_clarity (3 rules, weights 0.4 + 0.3 + 0.3 = 1.0)
        ChecklistRule(
            id="routing.single_intent_signal",
            description="query carries a single intent, not multiple chained operations",
            weight=0.40,
            sub_score="intent_clarity",
            check=check_single_intent_signal,
            citation="Sarikaya et al. (IEEE TASLP 2014) — intent detection in spoken NLU",
        ),
        ChecklistRule(
            id="routing.no_ambiguous_pronoun_lead",
            description="query does not start with a bare pronoun without antecedent",
            weight=0.30,
            sub_score="intent_clarity",
            check=check_no_ambiguous_pronoun_lead,
            citation=(
                "Industry banking routing-agent design pattern (production deployments, 2025)"
            ),
        ),
        ChecklistRule(
            id="routing.intent_shares_query_tokens",
            description="predicted intent shares at least one content token with the query",
            weight=0.30,
            sub_score="intent_clarity",
            check=check_intent_shares_query_tokens,
            citation="Wang et al. (ACL 2020) — intent-slot consistency for joint NLU",
        ),
        # classification_confidence (3 rules, weights 0.4 + 0.3 + 0.3 = 1.0)
        ChecklistRule(
            id="routing.top1_confidence_above_threshold",
            description="top-1 confidence above operational threshold (default 0.7)",
            weight=0.40,
            sub_score="classification_confidence",
            check=check_top1_confidence_above_threshold,
            citation="Guo et al. (ICML 2017) — on calibration of modern neural networks",
        ),
        ChecklistRule(
            id="routing.margin_to_runner_up",
            description="margin between top-1 and top-2 above floor (default 0.15)",
            weight=0.30,
            sub_score="classification_confidence",
            check=check_margin_to_runner_up,
            citation="Industry banking routing-agent evaluation — top-1 to top-2 margin metric",
        ),
        ChecklistRule(
            id="routing.intent_in_allowed_set",
            description="predicted intent belongs to the configured allowed set",
            weight=0.30,
            sub_score="classification_confidence",
            check=check_intent_in_allowed_set,
            citation="Hendrycks & Gimpel (ICLR 2017) — out-of-distribution detection",
        ),
        # fallback_appropriateness (2 rules, weights 0.6 + 0.4 = 1.0)
        ChecklistRule(
            id="routing.fallback_when_out_of_scope",
            description="if fallback fired, the query is actually out of scope",
            weight=0.60,
            sub_score="fallback_appropriateness",
            check=check_fallback_when_out_of_scope,
            citation="Industry banking RAG evaluation framework — fallback necessity check",
        ),
        ChecklistRule(
            id="routing.no_silent_fallback",
            description="fallback responses explain the limit instead of being silent",
            weight=0.40,
            sub_score="fallback_appropriateness",
            check=check_no_silent_fallback,
            citation="NIST AI RMF 1.0 (2023) §Govern 5 — transparency to affected parties",
        ),
        # disambiguation_quality (2 rules, weights 0.6 + 0.4 = 1.0)
        ChecklistRule(
            id="routing.clarify_when_ambiguous",
            description="low-margin cases trigger clarification rather than silent routing",
            weight=0.60,
            sub_score="disambiguation_quality",
            check=check_clarify_when_ambiguous,
            citation="Rao & Daumé III (ACL 2018) — learning to ask good questions",
        ),
        ChecklistRule(
            id="routing.specific_clarify_question",
            description="clarify question references the two candidate intents specifically",
            weight=0.40,
            sub_score="disambiguation_quality",
            check=check_specific_clarify_question,
            citation="De Vries et al. (ACL 2018) — task-oriented dialogue clarification",
        ),
    )

    return RuleSet(
        name="groundlens_routing_v1",
        rules=rules,
        sub_scores=(
            "intent_clarity",
            "classification_confidence",
            "fallback_appropriateness",
            "disambiguation_quality",
        ),
        flag_predicate=routing_flag_predicate,
    )
