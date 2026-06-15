"""Customer-support triage — rules for informational customer-facing agents.

Customer-support agents answer questions over a knowledge base (RAG mode) or
chat without retrieved context (no-RAG mode). Their failure modes differ from
the credit / AML / KYC decision rationales that
:func:`groundlens.rules.decision_rationale_rules` is calibrated for:

- **Fabricated numbers.** A wrong Bizum limit, a wrong APR, a wrong
  document requirement — these are operational hazards for the customer.
- **Fabricated proper nouns.** Wrong laws, wrong regulators, wrong
  procedures invented by the model.
- **Procedural overreach.** Adding steps that don't exist ("appointment
  with advisor"), inventing pricing tiers ("premium clients"), citing
  legal references not in the FAQ.

The rule set evaluates a customer-support response across up to three
sub-scores:

- ``groundedness`` — every number and every proper noun in the response
  appears in the FAQ context or the customer's query. *Only present when
  ``rag=True``; the rules require a context to compare against.*
- ``completeness`` — the response addresses the query topic and uses
  concrete values from the FAQ when relevant.
- ``no_overreach`` — the response does not add legal references or
  procedural details that are not in the FAQ.

The flag predicate is intentionally non-compensatory: a response that
fabricates facts or invents procedures is not partially safe.
``completeness`` is informational — under-informative-but-accurate
responses are flagged at the sub-score level for UX review but do not
trip the safety flag.

API
---

The canonical factory is :func:`customer_support_rules`. It accepts three
keyword arguments — ``rag``, ``domain``, ``language`` — that select the
right rule set for the deployment without renaming the function:

- ``rag=True`` (default) returns the full 7-rule, 3-sub-score set.
- ``rag=False`` omits the ``groundedness`` rules (no context to verify
  against) and returns a 4-rule, 2-sub-score set.
- ``domain`` extends the stopword / speculative-marker vocabulary with
  domain-specific surface forms ("finance", "healthcare", "legal", or
  the default "general").
- ``language`` adds Spanish or multilingual speculative markers and
  legal-reference patterns (defaults to "en").

The legacy alias :func:`customer_support_rag_rules` is preserved as a
``DeprecationWarning`` shim for at least three releases.

References:
    Torcal Villadangos, J. et al. (2026). AI Evaluation in the Age of
        Agents. BBVA AI Factory, 15 April 2026.

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
import warnings
from functools import partial
from typing import Any

from groundlens.rules import ChecklistRule, RuleEvidence, RuleSet

# ── Public catalogues (dimensions accepted by customer_support_rules) ──────


_VALID_DOMAINS: tuple[str, ...] = ("general", "finance", "healthcare", "legal")
_VALID_LANGUAGES: tuple[str, ...] = ("en", "es", "multi")


# ── Extractors ──────────────────────────────────────────────────────────────


_NUM_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?(?:%|\s?(?:EUR|euros?|days?|hours?|h|years?))?\b",
    re.IGNORECASE,
)

# Default stopwords (covers en + general banking-ish lexicon kept for
# backwards compatibility with the 2026.6.11 rule set).
_STOPWORDS_BASE: frozenset[str] = frozenset(
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

# Domain-specific stopword extensions.
_DOMAIN_STOPWORDS: dict[str, frozenset[str]] = {
    "general": frozenset(),
    "finance": frozenset({"TAE", "TIN", "Bizum", "SEPA", "SWIFT", "FROB", "CNMV", "AEAT"}),
    "healthcare": frozenset({"HSA", "FSA", "CPT", "NPI", "HIPAA"}),
    "legal": frozenset({"BOE", "BORME", "RD", "LO", "GDPR", "RGPD", "CCAA"}),
}

# Language-specific stopwords (proper-noun surface forms that should not be
# flagged as fabricated).
_LANG_STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset(),
    "es": frozenset({"España", "Europea", "Reino", "Madrid", "Barcelona"}),
    "multi": frozenset({"España", "Europea", "Reino", "Madrid", "Barcelona"}),
}


# Default speculative markers (en).
_SPECULATIVE_MARKERS_BASE: tuple[str, ...] = (
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

# Domain-specific markers extending the speculative-procedure check.
_DOMAIN_MARKERS: dict[str, tuple[str, ...]] = {
    "general": (),
    "finance": ("private banking tier", "concierge service", "wealth advisor"),
    "healthcare": ("co-pay tier", "out-of-network", "concierge medicine"),
    "legal": ("retainer agreement", "fee waiver", "expedited filing"),
}

# Language-specific markers.
_LANG_MARKERS: dict[str, tuple[str, ...]] = {
    "en": (),
    "es": (
        "cita previa con",
        "asesor personal",
        "horario comercial",
        "cliente premium",
        "atención preferente",
        "normalmente tarda",
    ),
    "multi": (
        "cita previa con",
        "asesor personal",
        "horario comercial",
        "cliente premium",
        "atención preferente",
        "normalmente tarda",
    ),
}


# Legal-reference regex per language. English keywords + Spanish keywords +
# multi (union) cover the cases we have seen in regulated FAQs.
_LEGAL_REF_RE_EN = re.compile(
    r"\b(?:Law|Directive|Modelo|Regulation|Act|Article|Rule)\s+\d",
    re.IGNORECASE,
)
_LEGAL_REF_RE_ES = re.compile(
    r"\b(?:Ley|Real\s+Decreto|RD|Orden|Reglamento|Art[ií]culo|Modelo)\s+\d",
    re.IGNORECASE,
)
_LEGAL_REF_RE_MULTI = re.compile(
    r"\b(?:Law|Directive|Modelo|Regulation|Act|Article|Rule|Ley|Real\s+Decreto|RD|Orden|Reglamento|Art[ií]culo)\s+\d",
    re.IGNORECASE,
)


def _legal_ref_re(language: str) -> re.Pattern[str]:
    if language == "es":
        return _LEGAL_REF_RE_ES
    if language == "multi":
        return _LEGAL_REF_RE_MULTI
    return _LEGAL_REF_RE_EN


def _build_stopwords(domain: str, language: str) -> frozenset[str]:
    return _STOPWORDS_BASE | _DOMAIN_STOPWORDS[domain] | _LANG_STOPWORDS[language]


def _build_speculative_markers(domain: str, language: str) -> tuple[str, ...]:
    return _SPECULATIVE_MARKERS_BASE + _DOMAIN_MARKERS[domain] + _LANG_MARKERS[language]


# ── Helpers (pure, deterministic) ───────────────────────────────────────────


def _extract_numbers(text: str) -> set[str]:
    """Extract numeric tokens, stripped to digits only for comparison."""
    raw = _NUM_RE.findall(text)
    return {re.sub(r"[^\d]", "", n.lower()) for n in raw if re.sub(r"[^\d]", "", n)}


def _extract_proper_nouns(text: str, stopwords: frozenset[str]) -> set[str]:
    """Extract capitalized tokens longer than 3 chars, minus the stopword list."""
    candidates = re.findall(r"\b[A-Z][a-zA-Z]+\b", text)
    return {c for c in candidates if c not in stopwords and len(c) > 3}


def _content_words(text: str, min_len: int = 4) -> set[str]:
    """Lowercase content words for surface overlap measurements."""
    return set(re.findall(rf"\b[a-z]{{{min_len},}}\b", text.lower()))


# ── Check function implementations ─────────────────────────────────────────


def _check_no_invented_numbers(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Every number in the response appears in the FAQ context or the query."""
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


def _check_no_invented_proper_nouns_impl(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
    *,
    stopwords: frozenset[str],
) -> RuleEvidence:
    """Every proper noun in the response appears in the FAQ context."""
    resp_p = _extract_proper_nouns(response, stopwords=stopwords)
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


def _check_content_overlaps_faq(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Content-word overlap between response and FAQ above 0.30."""
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


def _check_addresses_query_topic(
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


def _check_uses_concrete_values(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """If the FAQ has numbers, the response includes at least one of them."""
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


def _check_no_unrequested_legal_refs_impl(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
    *,
    legal_ref_re: re.Pattern[str],
) -> RuleEvidence:
    """No legal references in the response that are not in the FAQ."""
    resp_refs = set(legal_ref_re.findall(response))
    if not resp_refs:
        return RuleEvidence(matched=True, span="", explanation="no legal references — abstains")
    ctx_refs = set(legal_ref_re.findall(context or ""))
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


def _check_no_speculative_procedure_impl(
    question: str,
    response: str,
    context: str | None,
    metadata: dict[str, Any],
    *,
    speculative_markers: tuple[str, ...],
) -> RuleEvidence:
    """No procedural additions in the response that are not in the FAQ."""
    ctx_lower = (context or "").lower()
    resp_lower = response.lower()
    hits = [m for m in speculative_markers if m in resp_lower and m not in ctx_lower]
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


# ── Backwards-compatible top-level wrappers ────────────────────────────────
#
# The 2026.6.11 public API exported `check_*` functions with no kwargs.
# Downstream rule sets that imported those names directly should keep
# working. Internally they call the *_impl variants with the default
# (general, en) stopwords / markers / legal-ref pattern.


def check_no_invented_numbers(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Backwards-compatible wrapper for :func:`_check_no_invented_numbers`."""
    return _check_no_invented_numbers(question, response, context, metadata)


def check_no_invented_proper_nouns(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Backwards-compatible wrapper using the default (en, general) stopwords."""
    return _check_no_invented_proper_nouns_impl(
        question, response, context, metadata, stopwords=_STOPWORDS_BASE
    )


def check_content_overlaps_faq(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Backwards-compatible wrapper for :func:`_check_content_overlaps_faq`."""
    return _check_content_overlaps_faq(question, response, context, metadata)


def check_addresses_query_topic(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Backwards-compatible wrapper for :func:`_check_addresses_query_topic`."""
    return _check_addresses_query_topic(question, response, context, metadata)


def check_uses_concrete_values(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Backwards-compatible wrapper for :func:`_check_uses_concrete_values`."""
    return _check_uses_concrete_values(question, response, context, metadata)


def check_no_unrequested_legal_refs(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Backwards-compatible wrapper using the default (en) legal-reference regex."""
    return _check_no_unrequested_legal_refs_impl(
        question, response, context, metadata, legal_ref_re=_LEGAL_REF_RE_EN
    )


def check_no_speculative_procedure(
    question: str, response: str, context: str | None, metadata: dict[str, Any]
) -> RuleEvidence:
    """Backwards-compatible wrapper using the default (en, general) speculative markers."""
    return _check_no_speculative_procedure_impl(
        question, response, context, metadata, speculative_markers=_SPECULATIVE_MARKERS_BASE
    )


# ── Flag predicates ────────────────────────────────────────────────────────


def customer_support_flag_predicate(sub_scores: dict[str, float]) -> bool:
    """Flag iff groundedness or no_overreach collapse (RAG mode)."""
    return sub_scores.get("groundedness", 0.0) < 0.5 or sub_scores.get("no_overreach", 0.0) < 0.5


def _customer_support_no_rag_flag_predicate(sub_scores: dict[str, float]) -> bool:
    """Flag iff no_overreach collapses (no-RAG mode — no groundedness to check)."""
    return sub_scores.get("no_overreach", 0.0) < 0.5


# ── The rule set ────────────────────────────────────────────────────────────


def customer_support_rules(
    rag: bool = True,
    domain: str = "general",
    language: str = "en",
) -> RuleSet:
    """Rule set for customer-support informational agents.

    Designed for informational customer-facing assistants. Selects between
    the RAG and no-RAG sub-score taxonomies and adjusts the
    stopword / speculative-marker vocabulary to the deployment domain and
    language.

    Args:
        rag: Whether the agent retrieves context (FAQ) before answering.

            - ``True`` (default) — full 7-rule, 3-sub-score set
              (``groundedness``, ``completeness``, ``no_overreach``).
            - ``False`` — 4-rule, 2-sub-score set (``completeness``,
              ``no_overreach``). The three groundedness rules are omitted
              because there is no context to compare against. The flag
              predicate adapts.
        domain: Deployment domain. Affects stopwords and
            speculative-procedure markers; does not add or remove rules.

            One of: ``"general"`` (default), ``"finance"``,
            ``"healthcare"``, ``"legal"``.
        language: Deployment language. Affects stopwords,
            speculative-procedure markers, and the legal-reference
            regular expression.

            One of: ``"en"`` (default), ``"es"``, ``"multi"``.

    Returns:
        A :class:`RuleSet` whose name encodes the active configuration:
        ``customer_support_v2_{domain}_{language}_{rag|norag}``.

    Raises:
        ValueError: If ``domain`` is not in :data:`_VALID_DOMAINS` or
            ``language`` is not in :data:`_VALID_LANGUAGES`.

    Examples:
        Default — FAQ-RAG, general domain, English::

            from groundlens.agents import customer_support_rules

            rs = customer_support_rules()
            result = rs.evaluate(
                question="What is the Bizum daily limit?",
                response="The Bizum daily limit is 1,000 EUR per transaction.",
                context=(
                    "The daily Bizum transfer limit is 1,000 EUR per "
                    "transaction and 2,000 EUR per day in total."
                ),
            )
            assert not result.flagged

        No-RAG chat in Spanish finance vocabulary::

            rs = customer_support_rules(rag=False, domain="finance", language="es")
            assert "completeness" in rs.sub_scores
            assert "groundedness" not in rs.sub_scores
    """
    if domain not in _VALID_DOMAINS:
        msg = (
            f"customer_support_rules(domain={domain!r}) — supported domains are {_VALID_DOMAINS}."
        )
        raise ValueError(msg)
    if language not in _VALID_LANGUAGES:
        msg = (
            f"customer_support_rules(language={language!r}) — supported languages are "
            f"{_VALID_LANGUAGES}."
        )
        raise ValueError(msg)

    stopwords = _build_stopwords(domain=domain, language=language)
    markers = _build_speculative_markers(domain=domain, language=language)
    legal_ref_re = _legal_ref_re(language=language)

    # Bind the domain/language-specific knobs into the check callables.
    proper_nouns_check = partial(_check_no_invented_proper_nouns_impl, stopwords=stopwords)
    legal_refs_check = partial(_check_no_unrequested_legal_refs_impl, legal_ref_re=legal_ref_re)
    speculative_check = partial(_check_no_speculative_procedure_impl, speculative_markers=markers)

    grounded_rules: tuple[ChecklistRule, ...] = (
        ChecklistRule(
            id="csr.no_invented_numbers",
            description="every number in response appears in FAQ or query",
            weight=0.50,
            sub_score="groundedness",
            check=_check_no_invented_numbers,
            citation="Es et al. RAGAs (EACL 2024) §3 Faithfulness — atomic claim verification",
        ),
        ChecklistRule(
            id="csr.no_invented_proper_nouns",
            description="every proper noun in response appears in FAQ",
            weight=0.30,
            sub_score="groundedness",
            check=proper_nouns_check,
            citation="Min et al. FActScore (EMNLP 2023) — atomic factual precision",
        ),
        ChecklistRule(
            id="csr.content_overlaps_faq",
            description="response content overlaps FAQ above threshold",
            weight=0.20,
            sub_score="groundedness",
            check=_check_content_overlaps_faq,
            citation="Marin (2025) SGI arXiv:2512.13771 — surface grounding signal",
        ),
    )
    completeness_rules: tuple[ChecklistRule, ...] = (
        ChecklistRule(
            id="csr.addresses_query_topic",
            description="response addresses the query topic",
            weight=0.70,
            sub_score="completeness",
            check=_check_addresses_query_topic,
            citation="Industry banking RAG evaluation framework — relevance check",
        ),
        ChecklistRule(
            id="csr.uses_concrete_values",
            description="response uses concrete values from FAQ",
            weight=0.30,
            sub_score="completeness",
            check=_check_uses_concrete_values,
            citation="Industry banking RAG evaluation framework — usefulness check",
        ),
    )
    overreach_rules: tuple[ChecklistRule, ...] = (
        ChecklistRule(
            id="csr.no_unrequested_legal_refs",
            description="no legal references in response that are not in FAQ",
            weight=0.60,
            sub_score="no_overreach",
            check=legal_refs_check,
            citation="EU AI Act 2024/1689 Art. 13 — transparency on capabilities and limits",
        ),
        ChecklistRule(
            id="csr.no_speculative_procedure",
            description="no procedural additions not present in FAQ",
            weight=0.40,
            sub_score="no_overreach",
            check=speculative_check,
            citation="Federal Reserve SR 26-2 (Apr 2026) §model output controls",
        ),
    )

    rag_tag = "rag" if rag else "norag"
    name = f"customer_support_v2_{domain}_{language}_{rag_tag}"

    if rag:
        rules = grounded_rules + completeness_rules + overreach_rules
        return RuleSet(
            name=name,
            rules=rules,
            sub_scores=("groundedness", "completeness", "no_overreach"),
            flag_predicate=customer_support_flag_predicate,
        )
    rules = completeness_rules + overreach_rules
    return RuleSet(
        name=name,
        rules=rules,
        sub_scores=("completeness", "no_overreach"),
        flag_predicate=_customer_support_no_rag_flag_predicate,
    )


def customer_support_rag_rules() -> RuleSet:
    """Deprecated alias — use :func:`customer_support_rules` (with ``rag=True``).

    Preserved for one or more releases for backwards compatibility with
    code written against groundlens 2026.6.11 / 2026.6.12. The returned
    rule set is byte-for-byte identical to
    ``customer_support_rules(rag=True, domain="general", language="en")``
    except for the ``RuleSet.name`` field, which keeps the legacy
    ``"customer_support_rag_v1"`` value so existing audit logs continue to
    match.

    .. deprecated:: 2026.6.13
        Use :func:`customer_support_rules` instead.
    """
    warnings.warn(
        "customer_support_rag_rules() is deprecated; "
        "use customer_support_rules(rag=True) instead. "
        "The legacy alias will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    rs = customer_support_rules(rag=True, domain="general", language="en")
    # Preserve the legacy name so downstream code that asserts on rs.name
    # (e.g. the cookbook notebook's `ruleset.name` check) does not break.
    object.__setattr__(rs, "name", "customer_support_rag_v1")
    return rs
