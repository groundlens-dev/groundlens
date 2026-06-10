"""RAG agent triage — rule set for retrieval-augmented informational agents.

RAG agents retrieve from a knowledge base and generate a grounded
response. Their failure modes are well-studied in the literature:
fabrication of facts not in retrieved context, omission of relevant
context, miscalibration on out-of-knowledge queries, and missing
citations.

This module exposes :func:`rag_rules` as the agent-vocabulary entry
point for the rule set that already ships under the banking-specific
factory :func:`groundlens.rules.groundlens_banking_rules`. The current
20-rule set is grounded in the multi-source provenance framework
(*Defendable Rules for LLM Rationale Evaluation*, Marin, 2026) and
covers five sub-scores: groundedness, completeness, calibration,
traceability, robustness.

Naming choice: the current implementation is calibrated for banking
applications but the architecture and sub-scores are domain-agnostic.
A future refactor will let callers pass ``domain="banking"`` or
``domain="legal"`` to :func:`rag_rules` and have the underlying
rule weights and citations adapt accordingly. Until then, this is an
alias that gives callers vocabulary-consistency with
:func:`groundlens.agents.routing_rules` and
:func:`groundlens.agents.specialized_agent_rules`.

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

from groundlens.rules import RuleSet, groundlens_banking_rules


def rag_rules(domain: str = "banking") -> RuleSet:
    """Rule set for RAG / informational agents.

    Currently this returns :func:`groundlens.rules.groundlens_banking_rules`
    for any value of ``domain``. The signature accepts a domain
    argument to forward-compat with the planned multi-domain refactor
    (banking, legal, healthcare, insurance) without breaking call
    sites once the refactor lands.

    Args:
        domain: Reserved for future use. Currently must be ``"banking"``
            (default). Will raise ``ValueError`` for unsupported domains
            once verticalizations land.

    Returns:
        A :class:`RuleSet` with 20 rules across 5 sub-scores
        (groundedness, completeness, calibration, traceability,
        robustness).

    Example::

        from groundlens.agents import rag_rules

        rs = rag_rules()
        result = rs.evaluate(
            question="What is BBVA's Bizum daily limit?",
            response="The daily Bizum limit at BBVA is 1,000 EUR per transaction.",
            context=(
                "The daily Bizum transfer limit at BBVA is 1,000 EUR per "
                "transaction and 2,000 EUR per day in total."
            ),
        )
        assert not result.flagged
    """
    if domain != "banking":
        msg = (
            f"rag_rules(domain={domain!r}) — only 'banking' is currently supported. "
            "Verticalizations (legal, healthcare, insurance) are on the roadmap."
        )
        raise ValueError(msg)
    return groundlens_banking_rules()
