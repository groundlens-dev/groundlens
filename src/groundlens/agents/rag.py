"""RAG agent triage — rule set for retrieval-augmented informational agents.

RAG agents retrieve from a knowledge base and generate a grounded
response. Their failure modes are well-studied: fabrication of facts
not in retrieved context, omission of relevant context, miscalibration
on out-of-knowledge queries, and missing citations.

:func:`rag_rules` dispatches on a ``domain`` argument so the same
agent-vocabulary entry point covers multiple deployment archetypes:

- ``domain="banking"`` (default) — credit / AML / KYC decision rationales.
  Returns :func:`groundlens.rules.groundlens_banking_rules`.
- ``domain="customer_support"`` — informational customer-facing
  assistants over a FAQ knowledge base (the BBVA Blue archetype).
  Returns :func:`groundlens.agents.customer_support_rag_rules`.

References:
    Marin, J. (2026). Defendable Rules for LLM Rationale Evaluation in
        Banking Governance: A Multi-Source Provenance Framework.

    Es, S., James, J., Espinosa-Anke, L., & Schockaert, S. (2024).
        RAGAs: Automated Evaluation of Retrieval Augmented Generation.
        EACL 2024.

    Torcal Villadangos, J. et al. (2026). AI Evaluation in the Age of
        Agents. BBVA AI Factory, 15 April 2026.
"""

from __future__ import annotations

from groundlens.agents.customer_support import customer_support_rag_rules
from groundlens.rules import RuleSet, groundlens_banking_rules

_SUPPORTED_DOMAINS = ("banking", "customer_support")


def rag_rules(domain: str = "banking") -> RuleSet:
    """Rule set for RAG / informational agents.

    Args:
        domain: Which domain flavour to return.

            - ``"banking"`` (default): credit, AML, KYC, fraud, sanctions
              decision rationales. 20 rules across 5 sub-scores
              (groundedness, completeness, calibration, traceability,
              robustness). Same object as
              :func:`groundlens.rules.groundlens_banking_rules`.
            - ``"customer_support"``: informational customer-support RAG
              over a FAQ knowledge base. 7 rules across 3 sub-scores
              (groundedness, completeness, no_overreach). Same object as
              :func:`groundlens.agents.customer_support_rag_rules`.

    Returns:
        A :class:`RuleSet` calibrated for the requested domain.

    Raises:
        ValueError: If ``domain`` is not one of the supported domains.

    Example::

        from groundlens.agents import rag_rules

        # Default: banking decision rationales
        banking = rag_rules()  # or rag_rules(domain="banking")

        # Customer-support FAQ-RAG
        cs = rag_rules(domain="customer_support")
        result = cs.evaluate(
            question="What is the Bizum daily limit?",
            response="The Bizum daily limit at BBVA is 1,000 EUR per transaction.",
            context=(
                "The daily Bizum transfer limit at BBVA is 1,000 EUR per "
                "transaction and 2,000 EUR per day in total."
            ),
        )
        assert not result.flagged
    """
    if domain == "banking":
        return groundlens_banking_rules()
    if domain == "customer_support":
        return customer_support_rag_rules()
    msg = (
        f"rag_rules(domain={domain!r}) — supported domains are "
        f"{_SUPPORTED_DOMAINS}. Legal, healthcare, and insurance "
        "verticalizations are on the roadmap."
    )
    raise ValueError(msg)
