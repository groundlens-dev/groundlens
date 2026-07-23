"""The local DGI variant Gamma_k (query-specific reference direction)."""

from __future__ import annotations

import hashlib

import numpy as np

from groundlens import DGI, compute_dgi
from groundlens.dgi import _get_reference_bank, reset_calibration_cache


def _fake_encoder(texts: list[str]) -> np.ndarray:
    # Deterministic (seeded by text hash) 32-d vectors, so the bundled reference
    # set embeds into a stable space without a real model.
    out = np.zeros((len(texts), 32), dtype=np.float32)
    for i, t in enumerate(texts):
        seed = int(hashlib.md5(t.encode()).hexdigest()[:8], 16)
        out[i] = np.random.default_rng(seed).standard_normal(32).astype(np.float32)
    return out


def test_local_variant_runs_and_is_in_range() -> None:
    reset_calibration_cache()
    d = compute_dgi(
        question="What is compound interest?",
        response="Interest on the principal and on prior interest.",
        encoder=_fake_encoder,
        k=5,
    )
    assert -1.0 <= d.value <= 1.0
    reset_calibration_cache()


def test_local_equals_global_when_k_covers_the_whole_set() -> None:
    # With k >= N, mu_hat_q averages every reference displacement, which is the
    # global mu_hat. So Gamma_k must match global Gamma.
    reset_calibration_cache()
    q, r = "What is a bond?", "A bond is a loan made to a government or company."
    n = _get_reference_bank(encoder=_fake_encoder)[0].shape[0]
    g_local = compute_dgi(question=q, response=r, encoder=_fake_encoder, k=n + 1000)
    g_global = compute_dgi(question=q, response=r, encoder=_fake_encoder)
    assert abs(g_local.value - g_global.value) < 1e-3
    reset_calibration_cache()


def test_dgi_class_accepts_k() -> None:
    reset_calibration_cache()
    scorer = DGI(encoder=_fake_encoder, k=7)
    assert scorer.k == 7
    out = scorer.score("What is inflation?", "A general rise in prices over time.")
    assert -1.0 <= out.value <= 1.0
    reset_calibration_cache()
