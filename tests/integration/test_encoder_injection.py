"""Encoder injection, trust_remote_code resolution, and threshold fitting.

These tests run WITHOUT torch / sentence-transformers: a deterministic
fake encoder is injected so no model is ever downloaded. They are NOT
marked slow.
"""

from __future__ import annotations

import hashlib
import warnings
from typing import TYPE_CHECKING

import numpy as np
import pytest

import groundlens
from groundlens import (
    DEFAULT_MODEL,
    ThresholdFit,
    compute_dgi,
    compute_sgi,
    fit_thresholds,
    set_default_encoder,
)
from groundlens._internal.embeddings import _resolve_trust_remote_code
from groundlens._internal.thresholds import _mismatch_warned
from groundlens.calibrate import _youden_threshold
from groundlens.dgi import reset_calibration_cache
from groundlens.score import DGIResult, SGIResult

if TYPE_CHECKING:
    from collections.abc import Iterator


def fake_encoder(texts: list[str]) -> np.ndarray:
    """Deterministic bag-of-tokens hashing encoder (64 dims, no torch)."""

    def one(t: str) -> np.ndarray:
        v = np.zeros(64, np.float32)
        for _i, tok in enumerate((t or "").lower().split()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 64] += 1.0
        return v

    return np.vstack([one(t) for t in texts]).astype(np.float32)


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """Reset calibration cache, default encoder, and warn-once guard."""
    reset_calibration_cache()
    set_default_encoder(None)
    _mismatch_warned.clear()
    yield
    reset_calibration_cache()
    set_default_encoder(None)
    _mismatch_warned.clear()


def _no_sentence_transformers_imported() -> bool:
    import sys

    return "sentence_transformers" not in sys.modules


# ── (a) explicit encoder= argument ───────────────────────────────────────────


def test_compute_sgi_with_explicit_encoder() -> None:
    result = compute_sgi(
        question="What is the capital of France?",
        context="France is in Western Europe. Its capital is Paris.",
        response="The capital of France is Paris.",
        encoder=fake_encoder,
    )
    assert isinstance(result, SGIResult)
    assert np.isfinite(result.value)
    assert _no_sentence_transformers_imported()


def test_compute_dgi_with_explicit_encoder() -> None:
    result = compute_dgi(
        question="What causes seasons on Earth?",
        response="Seasons are caused by Earth's axial tilt.",
        encoder=fake_encoder,
    )
    assert isinstance(result, DGIResult)
    assert np.isfinite(result.value)
    assert _no_sentence_transformers_imported()


# ── (b) set_default_encoder is import-binding-proof ───────────────────────────


def test_set_default_encoder_applies_to_both() -> None:
    set_default_encoder(fake_encoder)
    sgi = compute_sgi(
        question="What is X?",
        context="X is a thing that does Y.",
        response="X does Y as described.",
    )
    dgi = compute_dgi(question="What is X?", response="X does Y as described.")
    assert isinstance(sgi, SGIResult)
    assert isinstance(dgi, DGIResult)
    assert _no_sentence_transformers_imported()

    # Clearing restores the default (sentence-transformers) path.
    set_default_encoder(None)
    assert groundlens.get_default_encoder() is None


# ── (c) _resolve_trust_remote_code ────────────────────────────────────────────


def test_resolve_trust_remote_code_default_model() -> None:
    assert _resolve_trust_remote_code(DEFAULT_MODEL, None) is True


def test_resolve_trust_remote_code_other_model() -> None:
    assert _resolve_trust_remote_code("all-MiniLM-L6-v2", None) is False


def test_resolve_trust_remote_code_override() -> None:
    assert _resolve_trust_remote_code(DEFAULT_MODEL, False) is False
    assert _resolve_trust_remote_code("all-MiniLM-L6-v2", True) is True


def test_resolve_trust_remote_code_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROUNDLENS_TRUST_REMOTE_CODE", "1")
    assert _resolve_trust_remote_code("all-MiniLM-L6-v2", None) is True
    monkeypatch.setenv("GROUNDLENS_TRUST_REMOTE_CODE", "false")
    assert _resolve_trust_remote_code("all-MiniLM-L6-v2", None) is False


# ── (d) fit_thresholds ────────────────────────────────────────────────────────


def _synthetic_examples() -> list[dict[str, object]]:
    context = "Paris is the capital of France and sits on the river Seine."
    examples: list[dict[str, object]] = []
    # Grounded: responses echo the context.
    for resp in [
        "Paris is the capital of France.",
        "The capital of France is Paris on the Seine.",
        "France's capital city is Paris.",
    ]:
        examples.append(
            {
                "question": "What is the capital of France?",
                "context": context,
                "response": resp,
                "label": 0,
            }
        )
    # Ungrounded: off-topic responses unrelated to the context.
    for resp in [
        "Bananas are an excellent source of potassium.",
        "The quarterly revenue grew by twelve percent.",
        "Photosynthesis converts sunlight into chemical energy.",
    ]:
        examples.append(
            {
                "question": "What is the capital of France?",
                "context": context,
                "response": resp,
                "label": 1,
            }
        )
    return examples


def test_fit_thresholds_returns_thresholdfit() -> None:
    set_default_encoder(fake_encoder)
    fit = fit_thresholds(_synthetic_examples())
    assert isinstance(fit, ThresholdFit)
    assert fit.n == 6
    assert fit.metric == "youden_j"
    assert fit.dgi_pass is not None
    assert np.isfinite(fit.dgi_pass)
    assert fit.sgi_review is not None
    assert np.isfinite(fit.sgi_review)
    assert _no_sentence_transformers_imported()


def test_youden_threshold_separates_clean_classes() -> None:
    # Perfectly separable: grounded high, hallucinated low. The chosen cutoff
    # must classify every example correctly under "value >= t is grounded".
    grounded = [0.8, 0.9, 1.0]
    hallucinated = [0.1, 0.2, 0.3]
    t = _youden_threshold(grounded, hallucinated)
    assert all(v >= t for v in grounded)
    assert all(v < t for v in hallucinated)


def test_fit_thresholds_maximizes_youden_j() -> None:
    # The fitted DGI threshold must achieve the maximal Youden's J over the
    # observed scores (no other cutoff can do strictly better).
    set_default_encoder(fake_encoder)
    examples = _synthetic_examples()
    fit = fit_thresholds(examples)
    assert fit.dgi_pass is not None

    g: list[float] = []
    h: list[float] = []
    for ex in examples:
        dgi = compute_dgi(str(ex["question"]), str(ex["response"]), encoder=fake_encoder)
        (h if ex["label"] == 1 else g).append(dgi.value)

    def youden_j(t: float) -> float:
        tpr = sum(v >= t for v in g) / len(g)
        tnr = sum(v < t for v in h) / len(h)
        return tpr + tnr

    best = youden_j(fit.dgi_pass)
    for t in [*g, *h]:
        assert youden_j(t) <= best + 1e-9


def test_fit_thresholds_requires_both_classes() -> None:
    set_default_encoder(fake_encoder)
    with pytest.raises(ValueError, match="both classes"):
        fit_thresholds(
            [{"question": "Q?", "response": "A.", "label": 0}],
        )


def test_fit_thresholds_no_context_omits_sgi() -> None:
    set_default_encoder(fake_encoder)
    examples: list[dict[str, object]] = [
        {"question": "Q1?", "response": "Q1? grounded answer here", "label": 0},
        {"question": "Q2?", "response": "completely unrelated banana text", "label": 1},
    ]
    fit = fit_thresholds(examples)
    assert fit.sgi_review is None
    assert fit.dgi_pass is not None


# ── (e) mismatch warning (warn-once) ──────────────────────────────────────────


def test_compute_sgi_warns_with_custom_encoder() -> None:
    with pytest.warns(UserWarning, match="bundled"):
        compute_sgi(
            question="What is X?",
            context="X is Y.",
            response="X is Y indeed.",
            encoder=fake_encoder,
        )


def test_compute_dgi_warns_with_custom_encoder() -> None:
    with pytest.warns(UserWarning, match="bundled"):
        compute_dgi(
            question="What is X?",
            response="X is Y indeed.",
            encoder=fake_encoder,
        )


def test_mismatch_warning_is_once_only() -> None:
    # First call warns (priming the guard).
    with pytest.warns(UserWarning, match="bundled"):
        compute_dgi(
            question="What is X?",
            response="X is Y indeed.",
            encoder=fake_encoder,
        )
    # A second identical call must NOT warn again.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compute_dgi(
            question="What is X again?",
            response="X is still Y indeed.",
            encoder=fake_encoder,
        )
    assert not [w for w in caught if issubclass(w.category, UserWarning)]
