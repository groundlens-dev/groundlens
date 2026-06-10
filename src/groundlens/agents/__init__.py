"""Agent triage — rule sets for the three agent classes in modern AI pipelines.

Modern AI systems are agentic pipelines, not single models. A production
deployment like BBVA's Blue assistant runs three agent classes in concert:

- **Routing / intent agents** classify the user's query into one of N
  candidate operations and decide whether to clarify or fall back.
- **RAG / informational agents** retrieve from a knowledge base and
  generate a grounded response.
- **Specialized / tool-using agents** capture entities (IBAN, amount,
  contact) from the dialogue and execute operations.

Each class has distinct failure modes and therefore distinct triage
needs. This submodule ships one rule set per class:

- :func:`routing_rules` — intent clarity, classification confidence,
  fallback appropriateness, disambiguation quality.
- :func:`rag_rules` — groundedness, completeness, calibration,
  traceability, robustness (currently aliases
  :func:`groundlens.rules.groundlens_banking_rules`).
- :func:`specialized_agent_rules` — entity groundedness, entity
  completeness, entity calibration, execution readiness.

All three rule sets follow the same deterministic, no-second-LLM,
citation-per-rule structure as the rest of Groundlens. They can be
composed: a Blue-style three-agent pipeline runs all three rule sets
in parallel, one per agent, and aggregates the audit trail.

References:
    Torcal Villadangos, J., Hernández Manzano, P., Falcón Leal, A.,
        López García-Romeu, A., & Dorado Alfaro, S. (2026). AI Evaluation
        in the Age of Agents. BBVA AI Factory, 15 April 2026.

    Falcón Leal, A., Torcal Villadangos, J., López García-Romeu, A.,
        Hernández Manzano, P., & Dorado Alfaro, S. (2025). Routing the
        future: How an intent agent simplifies banking interactions.
        BBVA AI Factory, 14 February 2025.

    Marin, J. (2026). Defendable Rules for LLM Rationale Evaluation in
        Banking Governance: A Multi-Source Provenance Framework.
"""

from __future__ import annotations

from groundlens.agents.customer_support import customer_support_rag_rules
from groundlens.agents.rag import rag_rules
from groundlens.agents.routing import routing_rules
from groundlens.agents.specialized import specialized_agent_rules

__all__ = [
    "customer_support_rag_rules",
    "rag_rules",
    "routing_rules",
    "specialized_agent_rules",
]
