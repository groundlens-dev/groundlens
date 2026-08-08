"""Groundlens — deterministic, offline checks for normative AI answers.

Groundlens takes an answer, the evidence it was supposed to be drawn from, and
a policy pack, and reports what does not line up: an obligation stated more
strongly than the evidence supports, a deadline that is not in the source, a
citation that does not resolve, a number that contradicts the record. It runs
on stdlib regex, ``decimal`` and ``hashlib``. There is no model in the decision
path, no floating point in the audit record and no wall clock, so the same
inputs produce byte-identical output on any machine, forever.

The verdict is :class:`~groundlens.types.Decision` — ``CLEAR`` or ``ESCALATE``.
Not a score. A number between zero and one cannot be defended in a regulatory
file; a list of findings with spans, rule ids and a content hash can.

Quick start::

    >>> from groundlens import check, load_pack
    >>> pack = load_pack("eu-retail-banking")            # doctest: +SKIP
    >>> result = check(                                   # doctest: +SKIP
    ...     answer="You must repay within 14 days.",
    ...     evidence=[("doc-1#p3", "The customer may repay within 30 days.")],
    ...     ruleset=pack,
    ...     metadata={"product_type": "loan", "disclosure_set": "v3"},
    ...     reference_date="2026-08-08",
    ... )
    >>> result.decision                                   # doctest: +SKIP
    <Decision.ESCALATE: 'escalate'>

Installing
----------

``pip install groundlens`` installs the control path and nothing else. Its only
runtime dependency is PyYAML, because a rule pack is a YAML file.

The embedding-geometry layer (SGI, DGI, calibration, encoders) is now an
extra::

    pip install "groundlens[geometry]"

Everything it exports is still reachable from this package —
``groundlens.compute_sgi``, ``groundlens.evaluate``, ``groundlens.calibrate``
and the rest — but it is resolved lazily (PEP 562), so ``import groundlens``
does not import numpy, sentence-transformers or torch. Touching one of those
names without the extra installed raises :class:`ImportError` naming the
install command. Note that lazy names are deliberately absent from ``__all__``:
``from groundlens import *`` will not drag in two gigabytes of tensors.

References:
    Marin (2025). Semantic Grounding Index. arXiv:2512.13771.
    Marin (2026). A Geometric Taxonomy of Hallucinations. arXiv:2602.13224v3.
    Marin (2026). How Transformers Reject Wrong Answers: Rotational Dynamics of
        Factual Constraint Processing. arXiv:2603.13259.
    Marin (2026). Defendable Rules for LLM Rationale Evaluation in Banking
        Governance: A Multi-Source Provenance Framework.
"""

from __future__ import annotations

import importlib
from typing import Any

from groundlens import agents, audit, rules
from groundlens._version import __version__
from groundlens.audit_record import AuditRecord
from groundlens.control import check
from groundlens.packs import Pack, load_pack
from groundlens.types import (
    Decision,
    Evidence,
    Fact,
    FactKind,
    Finding,
    Match,
    MatchState,
    Polarity,
    Result,
    Severity,
)

# ── Lazy geometry surface (PEP 562) ─────────────────────────────────────────
#
# name -> (module, attribute). Nothing here is imported until someone asks for
# it by name. Keep every module in this table inside the `geometry` extra's
# dependency footprint; anything on the control path belongs in the eager
# import block above.
_GEOMETRY_EXPORTS: dict[str, tuple[str, str]] = {
    # Scoring
    "SGI": ("groundlens.sgi", "SGI"),
    "compute_sgi": ("groundlens.sgi", "compute_sgi"),
    "DGI": ("groundlens.dgi", "DGI"),
    "compute_dgi": ("groundlens.dgi", "compute_dgi"),
    "evaluate": ("groundlens.evaluate", "evaluate"),
    "evaluate_batch": ("groundlens.evaluate", "evaluate_batch"),
    # Result types
    "SGIResult": ("groundlens.score", "SGIResult"),
    "DGIResult": ("groundlens.score", "DGIResult"),
    "GroundlensScore": ("groundlens.score", "GroundlensScore"),
    # Calibration
    "calibrate": ("groundlens.calibrate", "calibrate"),
    "CalibrationResult": ("groundlens.calibrate", "CalibrationResult"),
    "fit_thresholds": ("groundlens.calibrate", "fit_thresholds"),
    "ThresholdFit": ("groundlens.calibrate", "ThresholdFit"),
    # Thresholds
    "DGI_PASS": ("groundlens._internal.thresholds", "DGI_PASS"),
    "SGI_REVIEW": ("groundlens._internal.thresholds", "SGI_REVIEW"),
    "SGI_STRONG_PASS": ("groundlens._internal.thresholds", "SGI_STRONG_PASS"),
    "normalize_dgi": ("groundlens._internal.thresholds", "normalize_dgi"),
    "normalize_sgi": ("groundlens._internal.thresholds", "normalize_sgi"),
    # Encoders
    "DEFAULT_MODEL": ("groundlens._internal.embeddings", "DEFAULT_MODEL"),
    "LIGHTWEIGHT_MINILM": ("groundlens._internal.embeddings", "LIGHTWEIGHT_MINILM"),
    "MULTILINGUAL_E5": ("groundlens._internal.embeddings", "MULTILINGUAL_E5"),
    "MULTILINGUAL_MINI": ("groundlens._internal.embeddings", "MULTILINGUAL_MINI"),
    "EmbeddingFn": ("groundlens._internal.embeddings", "EmbeddingFn"),
    "get_default_encoder": ("groundlens._internal.embeddings", "get_default_encoder"),
    "set_default_encoder": ("groundlens._internal.embeddings", "set_default_encoder"),
    # Switch (stage-2 routing over geometric scores)
    "GroundingSwitch": ("groundlens.switch", "GroundingSwitch"),
    "SwitchAction": ("groundlens.switch", "SwitchAction"),
    "SwitchDecision": ("groundlens.switch", "SwitchDecision"),
    # Label proposal
    "ProposedLabel": ("groundlens.propose", "ProposedLabel"),
    "PropositionBatch": ("groundlens.propose", "PropositionBatch"),
    "SeedExample": ("groundlens.propose", "SeedExample"),
}

# Third-party modules that only the geometry extra installs. If one of these is
# what went missing, the user needs the extra; anything else is a real bug and
# must surface unchanged rather than be mislabelled as a packaging problem.
_GEOMETRY_DEPS = frozenset({"numpy", "sentence_transformers", "torch", "transformers"})

_GEOMETRY_HINT = (
    "groundlens.{name} needs the embedding-geometry extra, which is not "
    'installed. Run: pip install "groundlens[geometry]"\n'
    "(As of groundlens 2.0.0 the base install is the deterministic control "
    "path only. It has no numpy and no sentence-transformers, so it stays "
    "small enough to sit in a request path.)"
)

# `check` is a function in v2, but `groundlens/check.py` still exists as the v1
# module and `groundlens.switch` imports from it. Any `import groundlens.check`
# anywhere in the process rebinds the *attribute* `groundlens.check` to that
# module, silently replacing the entry point. Cheap to reassert, very expensive
# to debug.
_control_check = check


def _reassert_check() -> None:
    """Restore ``groundlens.check`` to the control entry point."""
    globals()["check"] = _control_check


def __getattr__(name: str) -> Any:
    """Resolve the geometry surface on first access (PEP 562)."""
    target = _GEOMETRY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute = target
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        if exc.name is not None and exc.name.split(".")[0] in _GEOMETRY_DEPS:
            raise ImportError(_GEOMETRY_HINT.format(name=name)) from exc
        raise
    finally:
        _reassert_check()

    value = getattr(module, attribute)
    globals()[name] = value
    _reassert_check()
    return value


def __dir__() -> list[str]:
    """List the eager exports plus the lazily resolved geometry names."""
    return sorted(set(__all__) | set(_GEOMETRY_EXPORTS))


__all__ = [
    "AuditRecord",
    "Decision",
    "Evidence",
    "Fact",
    "FactKind",
    "Finding",
    "Match",
    "MatchState",
    "Pack",
    "Polarity",
    "Result",
    "Severity",
    # Meta
    "__version__",
    # Submodules
    "agents",
    "audit",
    # Entry point
    "check",
    "load_pack",
    "rules",
]
