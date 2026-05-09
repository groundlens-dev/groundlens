"""AutoGen agent reply checker using groundlens.

Evaluates the last message in an AutoGen conversation for hallucination
risk and returns a structured result with score and flagged status.

Example:
    >>> from groundlens.integrations.autogen import GroundlensChecker
    >>> checker = GroundlensChecker()
    >>> result = checker.check(
    ...     messages=[
    ...         {"role": "user", "content": "What is X?"},
    ...         {"role": "assistant", "content": "X is Y."},
    ...     ],
    ...     sender=None,
    ... )
    >>> result["flagged"]
    False
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from groundlens.evaluate import evaluate

if TYPE_CHECKING:
    from groundlens.score import GroundlensScore

logger = logging.getLogger(__name__)


def _validate_autogen_available() -> None:
    """Verify that the autogen package is importable.

    Raises:
        ImportError: If the ``pyautogen`` package is not installed.
    """
    try:
        import autogen  # noqa: F401
    except ImportError as exc:
        msg = (
            "The 'pyautogen' package is required for GroundlensChecker. "
            "Install it with: pip install 'groundlens[autogen]'"
        )
        raise ImportError(msg) from exc


class GroundlensChecker:
    """AutoGen reply checker that evaluates messages with groundlens.

    Designed to be used as a reply validation step in AutoGen agent
    conversations. Evaluates the last assistant message against the
    preceding user message for hallucination risk.

    Args:
        groundlens_model: Sentence-transformer model for groundlens scoring.
            Defaults to ``"all-MiniLM-L6-v2"``.
        context_key: Key to look for context in message metadata.
            Defaults to ``"context"``.

    Example:
        >>> checker = GroundlensChecker()
        >>> messages = [
        ...     {"role": "user", "content": "Summarize this document."},
        ...     {"role": "assistant", "content": "The document discusses..."},
        ... ]
        >>> result = checker.check(messages, sender=None)
        >>> result["method"]
        'dgi'
        >>> result["flagged"]
        False
    """

    def __init__(
        self,
        groundlens_model: str = "all-MiniLM-L6-v2",
        context_key: str = "context",
    ) -> None:
        self._groundlens_model = groundlens_model
        self._context_key = context_key

    def check(
        self,
        messages: list[dict[str, Any]],
        sender: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Evaluate the last message in the conversation.

        Extracts the last assistant message as the response and the
        most recent preceding user message as the question. If context
        is found in message metadata, SGI scoring is used; otherwise
        DGI is applied.

        Args:
            messages: List of conversation message dicts. Each dict should
                have ``"role"`` and ``"content"`` keys.
            sender: The AutoGen agent that sent the last message.
                Used for logging; can be ``None``.
            **kwargs: Additional keyword arguments. If a ``"context"``
                key is present, it is used for SGI evaluation.

        Returns:
            A dict containing:
                - ``"score"``: The raw groundlens score value.
                - ``"normalized"``: Score mapped to [0, 1].
                - ``"flagged"``: Whether human review is recommended.
                - ``"method"``: Scoring method used (``"sgi"`` or ``"dgi"``).
                - ``"explanation"``: Human-readable interpretation.

        Example:
            >>> checker = GroundlensChecker()
            >>> result = checker.check(
            ...     messages=[
            ...         {"role": "user", "content": "What is 2+2?"},
            ...         {"role": "assistant", "content": "2+2 equals 4."},
            ...     ],
            ...     sender=None,
            ... )
            >>> isinstance(result["score"], float)
            True
        """
        if not messages:
            logger.warning("GroundlensChecker.check called with empty messages")
            return {
                "score": None,
                "normalized": None,
                "flagged": None,
                "method": None,
                "explanation": "No messages to evaluate.",
            }

        last_message = messages[-1]
        response = str(last_message.get("content", ""))

        question = ""
        for msg in reversed(messages[:-1]):
            if msg.get("role") == "user":
                question = str(msg.get("content", ""))
                break

        if not question:
            question = response

        context: str | None = kwargs.get(self._context_key)

        if context is None:
            for msg in reversed(messages):
                msg_metadata = msg.get("metadata", {})
                if isinstance(msg_metadata, dict) and self._context_key in msg_metadata:
                    context = str(msg_metadata[self._context_key])
                    break

        sender_name = getattr(sender, "name", str(sender)) if sender else "unknown"
        logger.debug(
            "GroundlensChecker.check sender=%s messages=%d context=%s",
            sender_name,
            len(messages),
            "provided" if context else "none",
        )

        score: GroundlensScore = evaluate(
            question=question,
            response=response,
            context=context,
            model=self._groundlens_model,
        )

        if score.flagged:
            logger.warning(
                "GroundlensChecker FLAGGED sender=%s method=%s value=%.3f — %s",
                sender_name,
                score.method,
                score.value,
                score.explanation,
            )
        else:
            logger.info(
                "GroundlensChecker OK sender=%s method=%s value=%.3f",
                sender_name,
                score.method,
                score.value,
            )

        return {
            "score": score.value,
            "normalized": score.normalized,
            "flagged": score.flagged,
            "method": score.method,
            "explanation": score.explanation,
        }
