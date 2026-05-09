"""Threshold constants and normalization functions.

All thresholds are derived empirically from the experiments reported
in arXiv:2512.13771 (SGI) and arXiv:2602.13224 (DGI).

These constants define the decision boundaries for flagging LLM outputs
as potential hallucinations. They are intentionally conservative: the
default behavior is to flag for human review rather than silently pass.
"""

from __future__ import annotations

import math

# ── SGI thresholds (arXiv:2512.13771) ───────────────────────────────────────
#
# SGI = dist(response, question) / dist(response, context)
#
# Interpretation:
#   SGI > 1.0  → response is closer to context than to question (grounded)
#   SGI < 1.0  → response is closer to question than to context (risk)
#   SGI ≈ 1.0  → equidistant (ambiguous)

SGI_STRONG_PASS: float = 1.20
"""SGI score indicating strong context engagement. Green zone."""

SGI_REVIEW: float = 0.95
"""SGI score below which output is flagged for human review. Red zone."""

# ── DGI thresholds (arXiv:2602.13224) ─────────────���──────────────��──────────
#
# DGI = dot(normalize(phi(r) - phi(q)), mu_hat)
#
# Interpretation:
#   DGI > 0.3  → displacement aligns with verified grounded patterns
#   DGI < 0.3  → displacement diverges from grounded patterns (risk)
#   DGI < 0.0  → displacement is opposite to grounded direction (high risk)

DGI_PASS: float = 0.30
"""DGI score indicating alignment with grounded reference direction. Green zone."""


# ── Normalization ──────────────────��─────────────────────────────────────────


def normalize_sgi(raw_sgi: float) -> float:
    """Normalize raw SGI score to [0, 1] range.

    Uses tanh mapping with offset to produce a smooth sigmoid curve:
        normalized = tanh(max(0, raw - 0.3))

    This maps the raw SGI range (~0.5 to ~2.0) into a [0, 1] range
    suitable for dashboards and threshold comparison.

    Mapping reference points:
        SGI 0.30 → 0.000 (floor)
        SGI 0.95 → 0.457 (review threshold)
        SGI 1.20 → 0.604 (strong pass)
        SGI 2.00 → 0.885 (very strong)

    Args:
        raw_sgi: The raw SGI ratio (q_dist / ctx_dist).

    Returns:
        Score in [0.0, 1.0].
    """
    shifted = max(0.0, raw_sgi - 0.3)
    return min(1.0, max(0.0, math.tanh(shifted)))


def normalize_dgi(raw_dgi: float) -> float:
    """Normalize raw DGI score from [-1, 1] to [0, 1] range.

    Simple linear mapping: normalized = (raw + 1) / 2.

    Mapping reference points:
        DGI -1.0 → 0.000 (opposite to grounded direction)
        DGI  0.0 → 0.500 (orthogonal)
        DGI  0.3 → 0.650 (pass threshold)
        DGI  1.0 → 1.000 (perfectly aligned)

    Args:
        raw_dgi: The raw DGI cosine similarity to reference direction.

    Returns:
        Score in [0.0, 1.0].
    """
    return min(1.0, max(0.0, (raw_dgi + 1.0) / 2.0))
