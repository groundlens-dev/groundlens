"""GroundLens: the verification and evidence layer for AI.

    >>> from groundlens import verify
    >>> record = verify(answer, evidence=[("policy.pdf#p3", passage)])
    >>> record.decision
    'FAIL'

A verifier produces evidence, never truth. A policy turns evidence into a
decision. The chain is sealed in a signed record. Nothing here opens a
network connection.
"""

from __future__ import annotations

from groundlens._engine import engine_version as _engine_version
from groundlens._types import (
    NOTE_CODES,
    Anchor,
    AnchorKind,
    Encoder,
    Evidence,
    OperatingPoint,
    Proofread,
    Span,
    WindowEncoding,
)
from groundlens.bundle import Bundle
from groundlens.calibrate import calibrate
from groundlens.policy import Policy
from groundlens.proofread import adaptive_k, as_evidence, proofread
from groundlens.record import Record
from groundlens.verify import verify

__version__ = "4.0.0"
ENGINE_VERSION = _engine_version()

__all__ = [
    "ENGINE_VERSION",
    "NOTE_CODES",
    "Anchor",
    "AnchorKind",
    "Bundle",
    "Encoder",
    "Evidence",
    "OperatingPoint",
    "Policy",
    "Proofread",
    "Record",
    "Span",
    "WindowEncoding",
    "__version__",
    "adaptive_k",
    "as_evidence",
    "calibrate",
    "proofread",
    "verify",
]
