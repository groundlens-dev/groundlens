"""Compliance mapping and audit-report generation for regulated deployments.

This module surfaces the standards a groundlens function is designed to
support, as machine-readable metadata. The mapping is attached at import
time via the :func:`maps_to` decorator, so a deployment engineer or
compliance officer can introspect at runtime which clauses of which
standards a particular scoring path is intended to satisfy::

    from groundlens import compute_sgi
    from groundlens.compliance import get_mapping

    mapping = get_mapping(compute_sgi)
    for ref in mapping.references:
        print(ref.standard, ref.clauses)
    # SR_11_7 ('§3 Model Validation', '§5 Documentation')
    # EU_AI_ACT ('Art. 13 Transparency', 'Art. 17 Quality Management')
    # NIST_AI_RMF ('MEASURE 2.5', 'MEASURE 4.2')

This is intentionally **declarative** metadata rather than automated
compliance verification. It documents the standards the implementation
team had in mind when building the function, with explicit clause
references that an auditor can cross-check against the actual code and
configuration. A mapping does not by itself certify compliance — it
makes the design intent inspectable.

Three regulatory frameworks are covered out of the box:

- **SR 11-7** — US Federal Reserve / OCC Supervisory Guidance on Model
  Risk Management (2011). The dominant US banking model-risk standard.
- **EU_AI_ACT** — Regulation (EU) 2024/1689, the EU Artificial
  Intelligence Act. High-risk system requirements apply to many
  financial / governance LLM deployments in the EU.
- **NIST_AI_RMF** — NIST AI Risk Management Framework 1.0 (2023).
  Voluntary in the US but globally referenced; structured around the
  Govern / Map / Measure / Manage functions.

A :class:`ComplianceReport` helper renders a per-evaluation summary in
Markdown suitable for inclusion in an audit packet.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

# ── Standard identifiers ────────────────────────────────────────────────────


SR_11_7: str = "SR_11_7"
"""Federal Reserve / OCC SR 11-7 — US bank model risk management standard."""

EU_AI_ACT: str = "EU_AI_ACT"
"""Regulation (EU) 2024/1689 — EU AI Act."""

NIST_AI_RMF: str = "NIST_AI_RMF"
"""NIST AI RMF 1.0 — voluntary AI risk management framework."""


SUPPORTED_STANDARDS: tuple[str, ...] = (SR_11_7, EU_AI_ACT, NIST_AI_RMF)
"""All standard identifiers currently understood by :func:`maps_to`."""


# ── Mapping types ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StandardReference:
    """A reference to one or more clauses of a single standard.

    Attributes:
        standard: One of :data:`SUPPORTED_STANDARDS`.
        clauses: Tuple of human-readable clause identifiers, e.g.
            ``("§3 Model Validation", "§5 Documentation")``.
    """

    standard: str
    clauses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComplianceMapping:
    """The complete compliance mapping of a single function.

    Attributes:
        fn_name: The ``__name__`` of the function this mapping was attached to.
        description: Optional short summary of what the function does, from
            the deployment's compliance perspective.
        references: Tuple of :class:`StandardReference`, one per standard.
    """

    fn_name: str
    description: str
    references: tuple[StandardReference, ...]

    def standards(self) -> tuple[str, ...]:
        """Return the list of standards covered by this mapping."""
        return tuple(ref.standard for ref in self.references)

    def clauses_for(self, standard: str) -> tuple[str, ...]:
        """Return the clauses claimed for a given standard, or empty tuple."""
        for ref in self.references:
            if ref.standard == standard:
                return ref.clauses
        return ()


# ── Decorator ───────────────────────────────────────────────────────────────


_F = TypeVar("_F", bound=Callable[..., Any])


def maps_to(
    *,
    description: str = "",
    sr_11_7: Sequence[str] | None = None,
    eu_ai_act: Sequence[str] | None = None,
    nist_ai_rmf: Sequence[str] | None = None,
) -> Callable[[_F], _F]:
    """Decorate a function with a compliance mapping.

    Attaches a :class:`ComplianceMapping` as the ``__compliance__``
    attribute of the decorated function. The function itself is not
    modified — wrapping is a no-op at call time.

    Args:
        description: Short summary of the function's compliance role.
        sr_11_7: SR 11-7 clauses this function is designed to support.
        eu_ai_act: EU AI Act articles supported.
        nist_ai_rmf: NIST AI RMF categories supported.

    Returns:
        A decorator that attaches the mapping and returns the original
        function unchanged.

    Example:
        >>> @maps_to(
        ...     description="Auditable hallucination triage",
        ...     sr_11_7=["§3 Model Validation"],
        ...     eu_ai_act=["Art. 13 Transparency"],
        ... )
        ... def compute_x(...):
        ...     ...
    """
    refs: list[StandardReference] = []
    if sr_11_7:
        refs.append(StandardReference(SR_11_7, tuple(sr_11_7)))
    if eu_ai_act:
        refs.append(StandardReference(EU_AI_ACT, tuple(eu_ai_act)))
    if nist_ai_rmf:
        refs.append(StandardReference(NIST_AI_RMF, tuple(nist_ai_rmf)))

    def decorator(fn: _F) -> _F:
        mapping = ComplianceMapping(
            fn_name=fn.__name__,
            description=description,
            references=tuple(refs),
        )
        fn.__compliance__ = mapping  # type: ignore[attr-defined]
        return fn

    return decorator


def get_mapping(fn: Callable[..., Any]) -> ComplianceMapping | None:
    """Return the compliance mapping attached to a function, or ``None``."""
    return getattr(fn, "__compliance__", None)


# ── Default mappings for the public API ─────────────────────────────────────
#
# These mappings document the design intent of the SGI/DGI/evaluate functions
# for regulated deployments. They are *not* guarantees of compliance — they
# are explicit references to the clauses the implementation was built to
# support, that an auditor can verify against the code.


_SGI_MAPPING = ComplianceMapping(
    fn_name="compute_sgi",
    description=(
        "Deterministic geometric grounding score for responses produced with "
        "retrieval context. Supports auditability and reproducibility "
        "requirements in regulated AI deployments by eliminating the second "
        "LLM from the verification loop."
    ),
    references=(
        StandardReference(
            SR_11_7,
            (
                "§3 Model Validation — outcomes analysis via deterministic scoring",
                "§5 Documentation — every evaluation reproducible byte-for-byte",
                "§7 Governance, Policies, and Controls — explicit thresholds",
            ),
        ),
        StandardReference(
            EU_AI_ACT,
            (
                "Art. 13 Transparency — human-readable explanation string",
                "Art. 14 Human Oversight — triage tool surfaces flagged outputs",
                "Art. 15 Accuracy, Robustness, Cybersecurity — deterministic scoring",
                "Art. 17 Quality Management — batch evaluation in CI/CD",
            ),
        ),
        StandardReference(
            NIST_AI_RMF,
            (
                "MEASURE 2.5 — trustworthiness characteristics tracking",
                "MEASURE 4.2 — operational metrics for monitoring",
                "MANAGE 4.1 — risk treatment via flagged-output review",
            ),
        ),
    ),
)


_DGI_MAPPING = ComplianceMapping(
    fn_name="compute_dgi",
    description=(
        "Context-free directional grounding score using calibrated reference "
        "direction. Domain-specific calibration converts generic detection "
        "into domain-expert detection without retraining a model."
    ),
    references=(
        StandardReference(
            SR_11_7,
            (
                "§3 Model Validation — calibration data version-tracked",
                "§5 Documentation — calibration sources documented per deployment",
            ),
        ),
        StandardReference(
            EU_AI_ACT,
            (
                "Art. 10 Data and Data Governance — calibration corpus documented",
                "Art. 13 Transparency — explanation string includes method and threshold",
                "Art. 14 Human Oversight — flagged outputs routed to review",
            ),
        ),
        StandardReference(
            NIST_AI_RMF,
            (
                "MAP 2.3 — context characterization via calibration corpus",
                "MEASURE 2.7 — performance monitoring against calibration",
            ),
        ),
    ),
)


_BANKING_RULES_MAPPING = ComplianceMapping(
    fn_name="banking_rules",
    description=(
        "Rule-based interpretable layer for governance rationale evaluation in "
        "regulated banking decisions. Surfaces specificity / explanatory linkage "
        "/ boundary shift sub-scores that a compliance officer can verify "
        "manually against the rationale text and the case parameters."
    ),
    references=(
        StandardReference(
            SR_11_7,
            (
                "§3 Model Validation — outcomes analysis at rationale level",
                "§5 Documentation — audit explanation per evaluation",
                "§7 Governance, Policies, and Controls — rule weights configurable",
            ),
        ),
        StandardReference(
            EU_AI_ACT,
            (
                "Art. 13 Transparency — per-rule evidence spans in audit log",
                "Art. 14 Human Oversight — flagged rationales routed to officer",
                "Art. 17 Quality Management — deterministic rule application",
            ),
        ),
        StandardReference(
            NIST_AI_RMF,
            (
                "GOVERN 1.4 — rule weights documented and versioned",
                "MEASURE 2.5 — sub-scores track interpretability",
                "MANAGE 4.1 — flagged outputs routed for treatment",
            ),
        ),
    ),
)


_AUDIT_LOG_MAPPING = ComplianceMapping(
    fn_name="AuditLog",
    description=(
        "Hash-chain immutable audit log persisting every evaluation. Each "
        "entry is cryptographically linked to its predecessor via SHA-256, "
        "so post-hoc tampering breaks chain verification."
    ),
    references=(
        StandardReference(
            SR_11_7,
            (
                "§5 Documentation — full traceability of every evaluation",
                "§7 Governance, Policies, and Controls — examinable audit trail",
            ),
        ),
        StandardReference(
            EU_AI_ACT,
            (
                "Art. 12 Record-keeping — automatic logging of system events",
                "Art. 13 Transparency — auditable decision history",
            ),
        ),
        StandardReference(
            NIST_AI_RMF,
            (
                "GOVERN 1.5 — audit trail design documented",
                "MEASURE 4.2 — operational metrics captured per entry",
            ),
        ),
    ),
)


# ── Report generation ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ReportEntry:
    """A single evaluation entry to include in a compliance report.

    Attributes:
        timestamp: ISO-8601 UTC timestamp of the evaluation.
        identifier: An opaque identifier (e.g. case_id, request_id).
        method: Which scoring method was used (``"sgi"``, ``"dgi"``,
            ``"rules"``, ``"hybrid"``).
        score: Numeric score (raw or normalized — convention chosen by
            the deployment).
        flagged: Whether the entry was flagged for review.
        notes: Optional short note (e.g. operator decision, root cause).
    """

    timestamp: str
    identifier: str
    method: str
    score: float
    flagged: bool
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ComplianceReport:
    """A Markdown-renderable compliance report.

    The report is structured around a single regulatory framework and
    describes a batch of evaluations against it, with summary statistics
    and the explicit clauses claimed by the underlying scoring functions.

    Attributes:
        framework: One of :data:`SUPPORTED_STANDARDS`.
        title: Short title for the report.
        description: One-paragraph description of scope and methodology.
        period_start: Period start (UTC date).
        period_end: Period end (UTC date).
        mappings: The compliance mappings of the functions covered by
            this report. Each mapping's clauses for ``framework`` are
            included in the rendered output.
        entries: All evaluation entries within the report period.
    """

    framework: str
    title: str
    description: str
    period_start: _dt.date
    period_end: _dt.date
    mappings: tuple[ComplianceMapping, ...]
    entries: tuple[ReportEntry, ...]

    def summary(self) -> dict[str, Any]:
        """Return summary statistics for the entries."""
        total = len(self.entries)
        flagged = sum(1 for e in self.entries if e.flagged)
        by_method: dict[str, int] = {}
        for e in self.entries:
            by_method[e.method] = by_method.get(e.method, 0) + 1
        return {
            "total_evaluations": total,
            "flagged": flagged,
            "flagged_rate": (flagged / total) if total > 0 else 0.0,
            "by_method": by_method,
        }

    def to_markdown(self) -> str:
        """Render the report as Markdown."""
        s = self.summary()
        lines: list[str] = []
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(
            f"**Framework:** {self.framework}  \n"
            f"**Period:** {self.period_start.isoformat()} → {self.period_end.isoformat()}  \n"
            f"**Generated:** {_dt.datetime.now(_dt.timezone.utc).isoformat()}"
        )
        lines.append("")
        lines.append("## Description")
        lines.append("")
        lines.append(self.description)
        lines.append("")
        lines.append("## Standards mapping")
        lines.append("")
        lines.append(f"The following groundlens functions are mapped to {self.framework} clauses:")
        lines.append("")
        for m in self.mappings:
            clauses = m.clauses_for(self.framework)
            if not clauses:
                continue
            lines.append(f"### `{m.fn_name}`")
            lines.append("")
            if m.description:
                lines.append(f"_{m.description}_")
                lines.append("")
            for c in clauses:
                lines.append(f"- {c}")
            lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Total evaluations: **{s['total_evaluations']}**")
        lines.append(f"- Flagged for review: **{s['flagged']}** ({s['flagged_rate'] * 100:.1f}%)")
        if s["by_method"]:
            method_str = ", ".join(f"{k}={v}" for k, v in sorted(s["by_method"].items()))
            lines.append(f"- By method: {method_str}")
        lines.append("")
        if self.entries:
            lines.append("## Evaluations")
            lines.append("")
            lines.append("| Timestamp | Identifier | Method | Score | Flagged | Notes |")
            lines.append("|---|---|---|---|---|---|")
            for e in self.entries:
                flag = "yes" if e.flagged else "no"
                notes = e.notes.replace("|", "\\|") if e.notes else ""
                lines.append(
                    f"| {e.timestamp} | {e.identifier} | {e.method} | "
                    f"{e.score:.3f} | {flag} | {notes} |"
                )
            lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(
            "_This report documents the design intent of the underlying "
            "scoring functions with explicit clause references. A clause "
            "reference is a statement of intent, not an automated proof "
            "of compliance. Review the implementation, configuration, "
            "and deployment to verify actual conformance._"
        )
        return "\n".join(lines)


# ── Public mapping accessors ────────────────────────────────────────────────


def sgi_compliance_mapping() -> ComplianceMapping:
    """Return the documented mapping for :func:`compute_sgi`."""
    return _SGI_MAPPING


def dgi_compliance_mapping() -> ComplianceMapping:
    """Return the documented mapping for :func:`compute_dgi`."""
    return _DGI_MAPPING


def banking_rules_compliance_mapping() -> ComplianceMapping:
    """Return the documented mapping for :func:`banking_rules`."""
    return _BANKING_RULES_MAPPING


def audit_log_compliance_mapping() -> ComplianceMapping:
    """Return the documented mapping for :class:`groundlens.audit.AuditLog`."""
    return _AUDIT_LOG_MAPPING


def all_mappings() -> tuple[ComplianceMapping, ...]:
    """Return all documented public-API mappings as a tuple."""
    return (
        _SGI_MAPPING,
        _DGI_MAPPING,
        _BANKING_RULES_MAPPING,
        _AUDIT_LOG_MAPPING,
    )


__all__ = [
    "EU_AI_ACT",
    "NIST_AI_RMF",
    "SR_11_7",
    "SUPPORTED_STANDARDS",
    "ComplianceMapping",
    "ComplianceReport",
    "ReportEntry",
    "StandardReference",
    "all_mappings",
    "audit_log_compliance_mapping",
    "banking_rules_compliance_mapping",
    "dgi_compliance_mapping",
    "get_mapping",
    "maps_to",
    "sgi_compliance_mapping",
]
