"""AutoGen integration for groundlens.

Provides a reply checker that evaluates agent messages for hallucination risk.
"""

from __future__ import annotations

from groundlens.integrations.autogen.checker import GroundlensChecker

__all__ = [
    "GroundlensChecker",
]
