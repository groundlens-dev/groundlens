"""Groundlens — A geometric lens on factual accuracy.

Deterministic LLM hallucination detection via embedding geometry.
No second LLM. Auditable. EU AI Act compliant.

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

References:
    Marin (2025). Semantic Grounding Index. arXiv:2512.13771.
    Marin (2026). A Geometric Taxonomy of Hallucinations. arXiv:2602.13224v3.
    Marin (2026). Rotational Dynamics of Factual Constraint Processing. arXiv:2603.13259.
"""

from groundlens import rules
from groundlens._version import __version__
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
    # Rule sets
    "banking_rules",
    "calibrate",
    "compute_dgi",
    # Functions
    "compute_sgi",
    "evaluate",
    "evaluate_batch",
    "groundlens_banking_rules",
    # Submodules
    "rules",
]
