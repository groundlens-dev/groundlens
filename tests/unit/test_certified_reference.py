"""The bundled certified DGI reference (mu_hat) and the encoder guard."""

from __future__ import annotations

import numpy as np

from groundlens._internal.embeddings import DEFAULT_MODEL
from groundlens._internal.reference import load_certified_reference
from groundlens._internal.thresholds import DGI_PASS
from groundlens.dgi import _get_mu_hat, reset_calibration_cache


def test_reference_is_unit_vector_for_default_encoder() -> None:
    ref = load_certified_reference()
    assert ref.embedding_model == DEFAULT_MODEL
    assert ref.embedding_dimensions == 768
    assert ref.mu_hat.shape == (768,)
    assert abs(float(np.linalg.norm(ref.mu_hat)) - 1.0) < 1e-5


def test_dgi_pass_matches_certified_threshold() -> None:
    # The hardcoded constant must stay tied to the certified reference.
    ref = load_certified_reference()
    assert round(ref.optimal_threshold, 3) == DGI_PASS


def test_default_path_uses_precomputed_reference_without_a_model() -> None:
    reset_calibration_cache()
    ref = load_certified_reference()
    mu = _get_mu_hat(DEFAULT_MODEL, None, encoder=None)  # no model load: certified path
    assert np.array_equal(mu, ref.mu_hat)


def test_custom_encoder_never_reuses_the_certified_vector() -> None:
    reset_calibration_cache()
    ref = load_certified_reference()

    def tiny_encoder(texts: list[str]) -> np.ndarray:
        rng = np.random.default_rng(0)
        return rng.standard_normal((len(texts), 8)).astype(np.float32)

    mu = _get_mu_hat(DEFAULT_MODEL, None, encoder=tiny_encoder)
    assert mu.shape == (8,)  # recomputed in the custom space, not the 768-dim certified one
    assert not np.array_equal(mu, ref.mu_hat)
    reset_calibration_cache()


def test_process_global_encoder_never_reuses_the_certified_vector() -> None:
    from groundlens import set_default_encoder

    reset_calibration_cache()
    ref = load_certified_reference()

    def tiny_global(texts: list[str]) -> np.ndarray:
        rng = np.random.default_rng(1)
        return rng.standard_normal((len(texts), 12)).astype(np.float32)

    set_default_encoder(tiny_global)
    try:
        mu = _get_mu_hat(DEFAULT_MODEL, None, encoder=None)  # param None, but a global is set
        assert mu.shape == (12,)  # recomputed in the global encoder's space
        assert not np.array_equal(mu, ref.mu_hat)
    finally:
        set_default_encoder(None)
        reset_calibration_cache()
