"""Groundlens — Verifiable agent triage.

Deterministic. Auditable. No second LLM in the loop.

Groundlens triages outputs from individual LLMs and from multi-agent
pipelines (routing, RAG, specialized / tool-using agents). Two layers:

- **Geometric layer.** SGI and DGI score grounding via embedding
  geometry, sub-second and deterministic. Apply to any agent's
  natural-language output.
- **Rule-based layer.** Domain-specific rule sets with per-rule
  citations to academic, industrial, and regulatory sources. Per-agent
  factories live in :mod:`groundlens.agents`:
  :func:`groundlens.agents.routing_rules`,
  :func:`groundlens.agents.rag_rules`,
  :func:`groundlens.agents.specialized_agent_rules`.

Quick start::

    >>> from groundlens import compute_sgi, compute_dgi, evaluate
    >>>
    >>> # With context (RAG verification) — uses SGI
    >>> result = compute_sgi(
    ...     question="What is the capital of France?",
    ...     context="France is in Western Europe. Its capital is Paris.",
    ...     response="The capital of France is Paris.",
    ... )
    >>> result.flagged
    False
    >>>
    >>> # Without context — uses DGI
    >>> result = compute_dgi(
    ...     question="What causes seasons?",
    ...     response="Seasons are caused by Earth's 23.5-degree axial tilt.",
    ... )
    >>> result.flagged
    False
    >>>
    >>> # Auto-select method
    >>> score = evaluate(question="Q?", response="A.", context="Source.")
    >>> score.method
    'sgi'
    >>>
    >>> # Agent-specific rule triage
    >>> from groundlens.agents import routing_rules, rag_rules, specialized_agent_rules
    >>> rag = rag_rules()
    >>> rag.name
    'groundlens_banking_v1'

References:
    Marin (2025). Semantic Grounding Index. arXiv:2512.13771.
    Marin (2026). A Geometric Taxonomy of Hallucinations. arXiv:2602.13224v3.
    Marin (2026). Rotational Dynamics of Factual Constraint Processing. arXiv:2603.13259.
    Marin (2026). Defendable Rules for LLM Rationale Evaluation in Banking Governance:
        A Multi-Source Provenance Framework.
"""

from groundlens import agents, rules
from groundlens._version import __version__
from groundlens.agents import (
    customer_support_rag_rules,
    rag_rules,
    routing_rules,
    specialized_agent_rules,
)
from groundlens.calibrate import CalibrationResult, calibrate
from groundlens.dgi import DGI, compute_dgi
from groundlens.evaluate import evaluate, evaluate_batch
from groundlens.rules import (
    ChecklistRule,
    RuleEvidence,
    RuleResult,
    RuleSet,
    RuleSetResult,
    banking_rules,
    groundlens_banking_rules,
)
from groundlens.score import DGIResult, GroundlensScore, SGIResult
from groundlens.sgi import SGI, compute_sgi

__all__ = [
    "DGI",
    # Classes
    "SGI",
    "CalibrationResult",
    "ChecklistRule",
    "DGIResult",
    "GroundlensScore",
    "RuleEvidence",
    "RuleResult",
    "RuleSet",
    "RuleSetResult",
    "SGIResult",
    # Meta
    "__version__",
    # Submodules
    "agents",
    # Rule sets (legacy + canonical)
    "banking_rules",
    "calibrate",
    "compute_dgi",
    # Functions
    "compute_sgi",
    "customer_support_rag_rules",
    "evaluate",
    "evaluate_batch",
    "groundlens_banking_rules",
    # Agent-class rule sets
    "rag_rules",
    "routing_rules",
    "rules",
    "specialized_agent_rules",
]
