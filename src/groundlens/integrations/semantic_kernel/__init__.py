"""Semantic Kernel integration for groundlens.

Provides a function invocation filter that evaluates function results
for hallucination risk.
"""

from __future__ import annotations

from groundlens.integrations.semantic_kernel.filter import GroundlensFilter

__all__ = [
    "GroundlensFilter",
]
