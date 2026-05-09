"""CrewAI integration for groundlens.

Provides a tool that CrewAI agents can use to self-verify their outputs.
"""

from __future__ import annotations

from groundlens.integrations.crewai.tool import GroundlensTool

__all__ = [
    "GroundlensTool",
]
