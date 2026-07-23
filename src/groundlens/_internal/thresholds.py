"""Threshold constants and normalization functions.

All thresholds are derived empirically from the experiments reported
in arXiv:2512.13771 (SGI) and arXiv:2602.13224v3 (DGI).

These constants define the decision boundaries for flagging LLM outputs
as potential hallucinations. They are intentionally conservative: the
default behavior is to flag for human review rather than silently pass.
"""

from __future__ import annotations

import math
import warnings

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

# ── DGI thresholds (arXiv:2602.13224v3) ─────────────���──────────────��──────────
#
# DGI = dot(normalize(phi(r) - phi(q)), mu_hat)
#
# Interpretation:
#   DGI >= 0.30  → aligns with grounded patterns (ok)
#   DGI < 0.30   → diverges from grounded patterns (risk)
# (single binary cut; operating point for the default sentence-t5-large encoder
#  on the bundled reference set. Recalibrate for another encoder or domain.)

DGI_PASS: float = 0.3
"""DGI at or above this reads as grounded (ok); below reads as not grounded (risk).
DGI is a single binary cut. Operating point for the default sentence-t5-large
encoder on the bundled reference set; recalibrate for another encoder or domain
(``fit_thresholds`` / ``DGI.calibrate``)."""


# ── Encoder / threshold mismatch warning ─────────────────────────────────────

# The bundled SGI/DGI thresholds and the bundled DGI ``mu_hat`` are calibrated
# for the default encoder/model. Scoring with a custom encoder or a non-default
# model while relying on the bundled constants is a silent footgun, so warn —
# but only ONCE per unique (func, model, encoder_provided) to avoid log spam.
_mismatch_warned: set[tuple[str, str, bool]] = set()


def _warn_default_thresholds_with_custom_encoder(
    func: str,
    model: str,
    encoder_provided: bool,
) -> None:
    """Warn once that bundled thresholds/mu_hat assume the default encoder.

    Args:
        func: Name of the calling scorer (e.g. ``"compute_sgi"``).
        model: The model name being used for scoring.
        encoder_provided: Whether a custom ``encoder`` callable was supplied.
    """
    key = (func, model, encoder_provided)
    if key in _mismatch_warned:
        return
    _mismatch_warned.add(key)
    warnings.warn(
        f"{func}() is using a non-default encoder/model "
        f"(model={model!r}, custom_encoder={encoder_provided}) but the "
        "bundled SGI/DGI thresholds and DGI mu_hat are calibrated for the "
        "default encoder. Calibrate your own with "
        "groundlens.fit_thresholds(...) / groundlens.calibrate(...) to get "
        "meaningful flags.",
        UserWarning,
        stacklevel=3,
    )


# ── Normalization ───────────────────────────────────────────────────────────


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
        DGI -1.0  → 0.000 (opposite to grounded direction)
        DGI  0.0  → 0.500 (orthogonal)
        DGI  0.30 → 0.650 (pass threshold)
        DGI  1.0  → 1.000 (perfectly aligned)

    Args:
        raw_dgi: The raw DGI cosine similarity to reference direction.

    Returns:
        Score in [0.0, 1.0].
    """
    return min(1.0, max(0.0, (raw_dgi + 1.0) / 2.0))
