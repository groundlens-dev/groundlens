"""Agent triage — rule sets for the three agent classes in modern AI pipelines.

Modern AI systems are agentic pipelines, not single models. A production
multi-agent deployment runs three agent classes in concert:

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
- :func:`customer_support_rules` — informational customer-facing agents,
  with or without RAG (see ``rag=`` kwarg).
- :func:`specialized_agent_rules` — entity groundedness, entity
  completeness, entity calibration, execution readiness.

Decision-rationale agents (credit / AML / KYC / sanctions) live in
:func:`groundlens.rules.decision_rationale_rules` rather than in
``agents.*`` because they do not retrieve from a knowledge base in the
RAG sense; they reason over a case file.

All rule sets follow the same deterministic, no-second-LLM,
citation-per-rule structure as the rest of Groundlens. They can be
composed: a multi-agent pipeline runs the relevant rule sets in
parallel, one per agent, and aggregates the audit trail.

Backwards compatibility
-----------------------

The 2026.6.11 / 2026.6.12 API names are preserved as deprecated aliases:

- :func:`customer_support_rag_rules` → use :func:`customer_support_rules`
  (with ``rag=True``).
- :func:`rag_rules` → use :func:`groundlens.rules.decision_rationale_rules`
  for credit / AML / KYC, or :func:`customer_support_rules` for FAQ-RAG.

The aliases emit a ``DeprecationWarning`` and will be removed in a future
release.

References:
    Marin, J. (2026). Defendable Rules for LLM Rationale Evaluation in
        Banking Governance: A Multi-Source Provenance Framework.
"""

from __future__ import annotations

from groundlens.agents.customer_support import (
    customer_support_rag_rules,
    customer_support_rules,
)
from groundlens.agents.rag import rag_rules
from groundlens.agents.routing import routing_rules
from groundlens.agents.specialized import specialized_agent_rules

__all__ = [
    "customer_support_rag_rules",  # deprecated alias — kept for back-compat
    "customer_support_rules",
    "rag_rules",  # deprecated dispatcher — kept for back-compat
    "routing_rules",
    "specialized_agent_rules",
]
