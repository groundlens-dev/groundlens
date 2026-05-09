"""Result types for groundlens scoring operations.

All scoring functions return typed dataclass instances that provide:

- ``value``: The raw score (SGI ratio or DGI cosine similarity).
- ``normalized``: Score mapped to [0, 1] for dashboard/threshold use.
- ``flagged``: Boolean indicating whether human review is recommended.
- ``explanation``: Human-readable interpretation string.
- ``method``: Which algorithm produced this result (``"sgi"`` or ``"dgi"``).

These types are immutable (frozen dataclasses) and fully serializable.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundlens._internal.thresholds import (
    DGI_PASS,
    SGI_REVIEW,
    SGI_STRONG_PASS,
)


@dataclass(frozen=True, slots=True)
class SGIResult:
    """Result of Semantic Grounding Index computation.

    SGI measures whether a response engaged with the provided context
    or stayed anchored to the question. Higher values indicate stronger
    context engagement (grounded).

    Attributes:
        value: Raw SGI score = dist(response, question) / dist(response, context).
        normalized: Score mapped to [0, 1] via tanh normalization.
        flagged: ``True`` if the score is below the review threshold.
        q_dist: Euclidean distance from response to question embedding.
        ctx_dist: Euclidean distance from response to context embedding.
        method: Always ``"sgi"``.
        explanation: Human-readable interpretation of the score.
    """

    value: float
    normalized: float
    flagged: bool
    q_dist: float
    ctx_dist: float
    method: str = "sgi"
    explanation: str = ""

    def __post_init__(self) -> None:
        """Generate explanation from score if not provided."""
        if not self.explanation:
            if self.value >= SGI_STRONG_PASS:
                expl = f"SGI={self.value:.3f} — strong context engagement (pass)"
            elif self.value >= SGI_REVIEW:
                expl = f"SGI={self.value:.3f} — partial engagement (review recommended)"
            else:
                expl = f"SGI={self.value:.3f} — weak context engagement (flagged)"
            object.__setattr__(self, "explanation", expl)


@dataclass(frozen=True, slots=True)
class DGIResult:
    """Result of Directional Grounding Index computation.

    DGI measures whether the question-to-response displacement vector
    aligns with the mean displacement of verified grounded pairs.
    Higher values indicate alignment with grounded patterns.

    Attributes:
        value: Raw DGI score = cosine similarity to reference direction.
            Range: [-1, 1].
        normalized: Score mapped to [0, 1] via linear normalization.
        flagged: ``True`` if the score is below the pass threshold.
        method: Always ``"dgi"``.
        explanation: Human-readable interpretation of the score.
    """

    value: float
    normalized: float
    flagged: bool
    method: str = "dgi"
    explanation: str = ""

    def __post_init__(self) -> None:
        """Generate explanation from score if not provided."""
        if not self.explanation:
            if self.value >= DGI_PASS:
                expl = f"DGI={self.value:.3f} — aligns with grounded patterns (pass)"
            elif self.value >= 0.0:
                expl = f"DGI={self.value:.3f} — weak alignment (flagged)"
            else:
                expl = f"DGI={self.value:.3f} — opposes grounded direction (high risk)"
            object.__setattr__(self, "explanation", expl)


@dataclass(frozen=True, slots=True)
class GroundlensScore:
    """Unified score container returned by high-level ``evaluate()`` calls.

    Wraps either an SGIResult or DGIResult with additional metadata.

    Attributes:
        value: Raw score from the underlying method.
        normalized: Score in [0, 1].
        flagged: Whether human review is recommended.
        method: ``"sgi"`` or ``"dgi"``.
        explanation: Human-readable interpretation.
        detail: The full SGIResult or DGIResult for method-specific fields.
    """

    value: float
    normalized: float
    flagged: bool
    method: str
    explanation: str
    detail: SGIResult | DGIResult
