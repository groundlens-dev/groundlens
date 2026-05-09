"""CrewAI tool for agent self-verification via groundlens.

Allows CrewAI agents to verify their own outputs for hallucination
risk before presenting them to users or other agents.

Example:
    >>> from groundlens.integrations.crewai import GroundlensTool
    >>> tool = GroundlensTool()
    >>> result = tool._run(
    ...     question="What is X?",
    ...     response="X is Y.",
    ...     context="According to the docs, X is Y.",
    ... )
    >>> print(result)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from groundlens.evaluate import evaluate

if TYPE_CHECKING:
    from groundlens.score import GroundlensScore

logger = logging.getLogger(__name__)


def _validate_crewai_available() -> None:
    """Verify that the crewai package is importable.

    Raises:
        ImportError: If the ``crewai`` package is not installed.
    """
    try:
        import crewai  # noqa: F401
    except ImportError as exc:
        msg = (
            "The 'crewai' package is required for GroundlensTool. "
            "Install it with: pip install 'groundlens[crewai]'"
        )
        raise ImportError(msg) from exc


class GroundlensTool:
    """CrewAI tool for verifying LLM outputs using groundlens.

    Extends the CrewAI tool pattern to let agents self-verify their
    outputs. The tool evaluates a question-response pair (with optional
    context) and returns a human-readable verification summary.

    Args:
        name: Tool name visible to the agent. Defaults to
            ``"groundlens_verify"``.
        description: Tool description for agent tool selection.
        groundlens_model: Sentence-transformer model for groundlens scoring.
            Defaults to ``"all-MiniLM-L6-v2"``.

    Example:
        >>> from groundlens.integrations.crewai import GroundlensTool
        >>> tool = GroundlensTool()
        >>> # Agent uses the tool to verify its own output
        >>> result = tool._run(
        ...     question="What causes rain?",
        ...     response="Rain is caused by condensation.",
        ...     context="Water cycle: evaporation, condensation, precipitation.",
        ... )
        >>> "PASS" in result or "FLAGGED" in result
        True
    """

    name: str = "groundlens_verify"
    description: str = (
        "Verify an LLM response for hallucination risk. "
        "Provide the question, response, and optionally the source context. "
        "Returns a verification result with a grounding score."
    )

    def __init__(
        self,
        name: str = "groundlens_verify",
        description: str | None = None,
        groundlens_model: str = "all-MiniLM-L6-v2",
    ) -> None:
        self.name = name
        if description is not None:
            self.description = description
        self._groundlens_model = groundlens_model

    def _run(
        self,
        question: str,
        response: str,
        context: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Evaluate a response for hallucination risk.

        Args:
            question: The original question or prompt.
            response: The LLM-generated response to verify.
            context: Optional source document. When provided, SGI scoring
                is used; otherwise DGI scoring is applied.
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            A formatted string containing the verification result,
            including method, score, status, and explanation.

        Example:
            >>> tool = GroundlensTool()
            >>> result = tool._run("What is 2+2?", "2+2 is 4.")
            >>> isinstance(result, str)
            True
        """
        logger.debug(
            "GroundlensTool._run question_len=%d response_len=%d context=%s",
            len(question),
            len(response),
            "provided" if context else "none",
        )

        score: GroundlensScore = evaluate(
            question=question,
            response=response,
            context=context,
            model=self._groundlens_model,
        )

        status = "FLAGGED" if score.flagged else "PASS"

        result = (
            f"Groundlens Verification Result\n"
            f"----------------------------\n"
            f"Method: {score.method.upper()}\n"
            f"Score: {score.value:.3f} (normalized: {score.normalized:.3f})\n"
            f"Status: {status}\n"
            f"Explanation: {score.explanation}\n"
        )

        if score.flagged:
            result += (
                "\nRecommendation: This response may contain hallucinated content. "
                "Consider revising with verified sources.\n"
            )

        logger.info(
            "GroundlensTool result: method=%s value=%.3f status=%s",
            score.method,
            score.value,
            status,
        )

        return result
