# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""GroundLens: guardrails for LLM answers.

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
from groundlens import integrations, judges, observe, signers, sinks
from groundlens._request import Evidence
from groundlens.policy import Policy
from groundlens.record import Record
from groundlens.run import RunRecord, verify_run
from groundlens.verifier import Verifier
from groundlens.verify import verify

__version__ = "5.3.0"
ENGINE_VERSION = _engine_version()

__all__ = [
    "ENGINE_VERSION",
    "Evidence",
    "Policy",
    "Record",
    "RunRecord",
    "Verifier",
    "__version__",
    "integrations",
    "judges",
    "observe",
    "signers",
    "sinks",
    "verify",
    "verify_run",
]
