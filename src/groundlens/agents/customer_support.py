"""Customer-support RAG triage — rules for informational customer-facing agents.

Customer-support RAG agents retrieve from a knowledge base of FAQs and
generate responses to customer queries about products, fees, procedures,
and policies. Their failure modes differ from the credit / AML / KYC decision
rationales that :func:`groundlens.rules.groundlens_banking_rules` is
calibrated for:

- **Fabricated numbers.** A wrong Bizum limit, a wrong APR, a wrong
  document requirement — these are operational hazards for the customer.
- **Fabricated proper nouns.** Wrong laws, wrong regulators, wrong
  procedures invented by the model.
- **Procedural overreach.** Adding steps that don't exist ("appointment
  with advisor"), inventing pricing tiers ("premium clients"), citing
  legal references not in the FAQ.

The rule set below evaluates a customer-support RAG response across three
sub-scores:

- ``groundedness`` — every number and every proper noun in the response
  appears in the FAQ context or the customer's query.
- ``completeness`` — the response addresses the query topic and uses
  concrete values from the FAQ when relevant.
- ``no_overreach`` — the response does not add legal references or
  procedural details that are not in the FAQ.

The flag predicate is intentionally non-compensatory on ``groundedness``
and ``no_overreach``: a response that fabricates facts or invents
procedures is not partially safe. ``completeness`` is informational —
under-informative-but-accurate responses (e.g. "the credit card has an
annual fee") are flagged at the sub-score level for UX review but do not
trip the safety flag.

References:
    Es, S., James, J., Espinosa-Anke, L., & Schockaert, S. (2024).
        RAGAs: Automated Evaluation of Retrieval Augmented Generation.
        EACL 2024.

    Min, S. et al. (2023). FActScore: Fine-grained Atomic Evaluation
        of Factual Precision in Long Form Text Generation. EMNLP 2023.

    Marin, J. (2025). Semantic Grounding Index for LLM Hallucination
        Detection. arXiv:2512.13771.
"""

from __future__ import annotations

import re
from typing import Any

from groundlens.rules import ChecklistRule, RuleEvidence, RuleSet

# ── Extractors ──────────────────────────────────────────────────────────────


_NUM_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?(?:%|\s?(?:EUR|euros?|days?|hours?|h|years?))?\b",
    re.IGNORECASE,
)

_STOPWORDS = frozenset(
    {
        "Spanish",
        "European",
        "EUR",
        "Spain",
        "EU",
        "IBAN",
        "DNI",
        "NIE",
        "APR",
        "FAQ",
    }
)

_SPECULATIVE_MARKERS = (
    "appointment with",
    "by email",
    "via mail",
    "premium clients",
    "premium customers",
    "enterprise account",
    "business hours",
    "normally takes",
    "typically a",
    "as a courtesy",
)

_LEGAL_REF_RE = re.compile(
    r"\b(?:Law|Directive|Modelo|Regulation|Act|Article|Rule)\s+\d",
    re.IGNORECASE,
)


def _extract_numbers(text: str) -> set[str]:
    """Extract numeric tokens, stripped to digits only for comparison."""
    raw = _NUM_RE.findall(text)
    return {re.sub(r"[^\d]", "", n.lower()) for n in raw if re.sub(r"[^\d]", "", n)}


def _extract_proper_nouns(text: str) -> set[str]:
    """Extract capitalized tokens longer than 3 chars, minus a stopword list."""
    candidates = re.findall(r"\b[A-Z][a-zA-Z]+\b", text)
    return {c for c in candidates if c not in _STOPWORDS and len(c) > 3}


def _content_words(text: str, min_len: int = 4) -> set[str]:
    """Lowercase content words for surface overlap measurements."""
    return set(re.findall(rf"\b[a-z]{{{min_len},}}\b", text.lower()))


# ── Check functions ────────────────────────────────────────────────────────


def check_no_invented_numbers(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Every number in the response appears in the FAQ context or the query.

    This is the single most useful anti-fabrication check for
    informational customer-support responses: wrong numbers (fees,
    limits, deadlines, document counts) are the most common and most
    operationally dangerous form of fabrication in this domain.
    """
    resp_nums = _extract_numbers(response)
    if not resp_nums:
        return RuleEvidence(matched=True, span="", explanation="no numbers in response — abstains")
    ctx_nums = _extract_numbers(context or "")
    q_nums = _extract_numbers(question)
    invented = resp_nums - ctx_nums - q_nums
    if invented:
        return RuleEvidence(
            matched=False,
            span=", ".join(sorted(invented)[:5]),
            explanation="numbers in response not present in FAQ or query (fabrication)",
        )
    return RuleEvidence(
        matched=True,
        span=f"{len(resp_nums)} verified",
        explanation="every number in response is grounded in FAQ or query",
    )


def check_no_invented_proper_nouns(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Every proper noun in the response appears in the FAQ context.

    Catches fabricated organizations ("Bank of Spain Financial Crime
    Unit"), fabricated regulators, fabricated procedure names.
    """
    resp_p = _extract_proper_nouns(response)
    if not resp_p:
        return RuleEvidence(matched=True, span="", explanation="no proper nouns — abstains")
    ctx_lower = (context or "").lower()
    invented = {p for p in resp_p if p.lower() not in ctx_lower}
    if invented:
        return RuleEvidence(
            matched=False,
            span=", ".join(sorted(invented)[:5]),
            explanation="proper nouns in response not in FAQ (likely fabricated)",
        )
    return RuleEvidence(
        matched=True,
        span=f"{len(resp_p)} verified",
        explanation="every proper noun in response is grounded in FAQ",
    )


def check_content_overlaps_faq(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Content-word overlap between response and FAQ above 0.30.

    Cheap surface-level grounding signal. A response that shares almost
    no content vocabulary with the FAQ has either changed topic or
    ignored the retrieved context.
    """
    if not context:
        return RuleEvidence(matched=True, span="", explanation="no context — abstains")
    r_words = _content_words(response)
    c_words = _content_words(context)
    if not r_words:
        return RuleEvidence(matched=True, span="", explanation="no content words")
    overlap = len(r_words & c_words) / len(r_words)
    return RuleEvidence(
        matched=overlap >= 0.30,
        span=f"overlap={overlap:.2f}",
        explanation="content overlap with FAQ",
    )


def check_addresses_query_topic(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Response shares content words with the customer's query."""
    q_words = _content_words(question)
    r_words = _content_words(response)
    if not q_words:
        return RuleEvidence(matched=True, span="", explanation="empty query")
    overlap = len(q_words & r_words) / len(q_words)
    return RuleEvidence(
        matched=overlap >= 0.30,
        span=f"q-overlap={overlap:.2f}",
        explanation="response addresses the customer's query topic",
    )


def check_uses_concrete_values(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """If the FAQ has numbers, the response includes at least one of them.

    Catches the "vague but accurate" failure mode: a response that says
    "the credit card has an annual fee" when the FAQ specifies the exact
    amount (35 EUR) is under-informative.
    """
    ctx_nums = _extract_numbers(context or "")
    if not ctx_nums:
        return RuleEvidence(matched=True, span="", explanation="FAQ has no numbers — abstains")
    resp_nums = _extract_numbers(response)
    matched = bool(resp_nums & ctx_nums)
    return RuleEvidence(
        matched=matched,
        span=f"{len(resp_nums & ctx_nums)} concrete",
        explanation="response includes concrete values from FAQ",
    )


def check_no_unrequested_legal_refs(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """No legal / regulatory references in the response that are not in the FAQ.

    Catches fabricated law numbers and directive references — a common
    failure when the model fills procedural responses with plausible-sounding
    but invented citations.
    """
    resp_refs = set(_LEGAL_REF_RE.findall(response))
    if not resp_refs:
        return RuleEvidence(matched=True, span="", explanation="no legal references — abstains")
    ctx_refs = set(_LEGAL_REF_RE.findall(context or ""))
    unrequested = resp_refs - ctx_refs
    if unrequested:
        return RuleEvidence(
            matched=False,
            span=", ".join(sorted(unrequested)[:3]),
            explanation="legal references not present in FAQ (likely fabricated)",
        )
    return RuleEvidence(
        matched=True,
        span="all refs grounded",
        explanation="legal references match FAQ",
    )


def check_no_speculative_procedure(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """No procedural additions in the response that are not in the FAQ.

    Catches "appointment with advisor", "premium clients", and other
    plausible-but-invented procedural details that drift from the FAQ.
    """
    ctx_lower = (context or "").lower()
    resp_lower = response.lower()
    hits = [m for m in _SPECULATIVE_MARKERS if m in resp_lower and m not in ctx_lower]
    if hits:
        return RuleEvidence(
            matched=False,
            span=", ".join(hits[:3]),
            explanation="procedural additions not present in FAQ",
        )
    return RuleEvidence(
        matched=True,
        span="",
        explanation="no speculative procedural additions",
    )


# ── Flag predicate ──────────────────────────────────────────────────────────


def customer_support_flag_predicate(sub_scores: dict[str, float]) -> bool:
    """Flag iff groundedness or no_overreach collapse.

    Completeness is intentionally not in the predicate: a response that
    is correct but vague (e.g. "the credit card has an annual fee") is a
    UX issue, not a safety issue. Under-informative responses are
    surfaced via the completeness sub-score for human review without
    tripping the auto-flag.
    """
    return sub_scores.get("groundedness", 0.0) < 0.5 or sub_scores.get("no_overreach", 0.0) < 0.5


# ── The rule set ────────────────────────────────────────────────────────────


def customer_support_rag_rules() -> RuleSet:
    """Rule set for customer-support RAG / informational agents.

    Returns a 7-rule set across 3 sub-scores: groundedness, completeness,
    no_overreach. Each rule carries a citation to its academic, industrial,
    or regulatory source.

    Designed for informational customer-facing assistants over a FAQ-style
    knowledge base — the FAQ-RAG customer-support archetype. Not appropriate for credit /
    AML / KYC decision rationales (use
    :func:`groundlens.rules.groundlens_banking_rules` instead) nor for
    routing or specialized / tool-using agents (see
    :func:`groundlens.agents.routing_rules` and
    :func:`groundlens.agents.specialized_agent_rules`).

    Example::

        from groundlens.agents import customer_support_rag_rules

        rs = customer_support_rag_rules()
        result = rs.evaluate(
            question="What is the Bizum daily limit?",
            response="The Bizum daily limit is 1,000 EUR per transaction.",
            context=(
                "The daily Bizum transfer limit is 1,000 EUR per "
                "transaction and 2,000 EUR per day in total."
            ),
        )
        assert not result.flagged
    """
    rules = (
        # groundedness (3 rules, weights 0.5 + 0.3 + 0.2 = 1.0)
        ChecklistRule(
            id="csr.no_invented_numbers",
            description="every number in response appears in FAQ or query",
            weight=0.50,
            sub_score="groundedness",
            check=check_no_invented_numbers,
            citation="Es et al. RAGAs (EACL 2024) §3 Faithfulness — atomic claim verification",
        ),
        ChecklistRule(
            id="csr.no_invented_proper_nouns",
            description="every proper noun in response appears in FAQ",
            weight=0.30,
            sub_score="groundedness",
            check=check_no_invented_proper_nouns,
            citation="Min et al. FActScore (EMNLP 2023) — atomic factual precision",
        ),
        ChecklistRule(
            id="csr.content_overlaps_faq",
            description="response content overlaps FAQ above threshold",
            weight=0.20,
            sub_score="groundedness",
            check=check_content_overlaps_faq,
            citation="Marin (2025) SGI arXiv:2512.13771 — surface grounding signal",
        ),
        # completeness (2 rules, weights 0.7 + 0.3 = 1.0)
        ChecklistRule(
            id="csr.addresses_query_topic",
            description="response addresses the query topic",
            weight=0.70,
            sub_score="completeness",
            check=check_addresses_query_topic,
            citation="Industry banking RAG evaluation framework — relevance check",
        ),
        ChecklistRule(
            id="csr.uses_concrete_values",
            description="response uses concrete values from FAQ",
            weight=0.30,
            sub_score="completeness",
            check=check_uses_concrete_values,
            citation="Industry banking RAG evaluation framework — usefulness check",
        ),
        # no_overreach (2 rules, weights 0.6 + 0.4 = 1.0)
        ChecklistRule(
            id="csr.no_unrequested_legal_refs",
            description="no legal references in response that are not in FAQ",
            weight=0.60,
            sub_score="no_overreach",
            check=check_no_unrequested_legal_refs,
            citation=("EU AI Act 2024/1689 Art. 13 — transparency on capabilities and limits"),
        ),
        ChecklistRule(
            id="csr.no_speculative_procedure",
            description="no procedural additions not present in FAQ",
            weight=0.40,
            sub_score="no_overreach",
            check=check_no_speculative_procedure,
            citation="Federal Reserve SR 26-2 (Apr 2026) §model output controls",
        ),
    )

    return RuleSet(
        name="customer_support_rag_v1",
        rules=rules,
        sub_scores=("groundedness", "completeness", "no_overreach"),
        flag_predicate=customer_support_flag_predicate,
    )
