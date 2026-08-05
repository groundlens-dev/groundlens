"""The shipped DGI direction must be present, well-formed, and match its CSV.

None of this loads the encoder. It checks the *contract* of the shipped
artifact: that it exists, that it is one unit vector of the recorded width, that
the SHA-256 it records for ``reference_pairs.csv`` is the CSV actually
installed, and that the loader takes it for the default configuration and
refuses it for every other one.

Whether the vector is the *right* vector is a different question and costs an
encoder to answer. That is ``tests/integration/test_frozen_mu_hat.py``.

The split matters. The expensive test proves the derivation once, in the golden
job. These run in milliseconds on every push, and they catch the failure that is
actually likely: someone edits ``reference_pairs.csv`` and does not regenerate.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from importlib.resources import files

import numpy as np
import pytest

from groundlens._internal.embeddings import DEFAULT_MODEL
from groundlens.dgi import _FROZEN_META, _FROZEN_MU_HAT, _load_frozen_mu_hat

DATA = files("groundlens.data")


def _meta() -> dict[str, object]:
    return json.loads((DATA / _FROZEN_META).read_text(encoding="utf-8"))


def test_the_artifact_ships() -> None:
    """A missing file degrades silently to a 7m43s derivation on every process."""
    assert (DATA / _FROZEN_MU_HAT).is_file(), (
        f"{_FROZEN_MU_HAT} is not in package data. Without it every process "
        "re-embeds 424 texts on its first DGI call. Regenerate with "
        "`python -m groundlens.tools.freeze_mu_hat`."
    )
    assert (DATA / _FROZEN_META).is_file(), f"{_FROZEN_META} is not in package data"


def test_it_is_one_unit_vector_of_the_recorded_width() -> None:
    """DGI is a cosine against this vector. A non-unit vector is not a cosine."""
    with (DATA / _FROZEN_MU_HAT).open("rb") as fh:
        mu = np.load(fh, allow_pickle=False)
    meta = _meta()
    assert mu.ndim == 1, f"expected one vector, got shape {mu.shape}"
    assert mu.shape[0] == meta["dims"], f"{mu.shape[0]} dims, metadata says {meta['dims']}"
    assert float(np.linalg.norm(mu)) == pytest.approx(1.0, abs=1e-5)


def test_the_recorded_hash_is_the_csv_that_shipped() -> None:
    """The one failure that is actually likely: edit the CSV, forget to refit.

    A frozen direction is a claim about a corpus. If the corpus changes and the
    vector does not, the claim is false and nothing else in the suite notices —
    every score stays finite, ordered and plausible.
    """
    digest = hashlib.sha256((DATA / "reference_pairs.csv").read_bytes()).hexdigest()
    assert digest == _meta()["reference_pairs_sha256"], (
        "reference_pairs.csv has changed since the DGI direction was fitted. "
        "Run `python -m groundlens.tools.freeze_mu_hat` and commit both files."
    )


def test_the_metadata_names_the_encoder_it_was_fitted_on() -> None:
    """A direction from one embedding space is meaningless in another."""
    assert _meta()["encoder"] == DEFAULT_MODEL


def test_the_loader_takes_it_for_the_default_configuration() -> None:
    """The whole point. If this returns None, nobody gets the speedup."""
    mu = _load_frozen_mu_hat(DEFAULT_MODEL, None, None)
    assert mu is not None, "the loader rejected the shipped direction for the default config"
    assert mu.dtype == np.float32


@pytest.mark.parametrize(
    ("model_name", "reference_csv", "why"),
    [
        (DEFAULT_MODEL, "/some/user.csv", "a user CSV is a different corpus"),
        ("some/other-encoder", None, "another encoder is a different space"),
    ],
)
def test_the_loader_refuses_every_other_configuration(
    model_name: str, reference_csv: str | None, why: str
) -> None:
    """Silently reusing the bundled direction elsewhere is the dangerous bug."""
    assert _load_frozen_mu_hat(model_name, reference_csv, None) is None, why


def test_the_loader_refuses_a_custom_encoder() -> None:
    """Explicit encoder — its space is not the one this vector was fitted in."""

    def encoder(texts: list[str]) -> np.ndarray:  # pragma: no cover - never called
        raise AssertionError("must not be called")

    assert _load_frozen_mu_hat(DEFAULT_MODEL, None, encoder) is None


def test_the_loader_refuses_a_process_global_encoder() -> None:
    """set_default_encoder() is a hidden second input to encode_texts.

    ``_active_encoder_id`` folds it into the cache key for exactly this reason.
    The frozen loader has to see it too, or a process that installed its own
    encoder scores against a direction from a foreign embedding space.
    """
    import groundlens

    def encoder(texts: list[str]) -> np.ndarray:  # pragma: no cover - never called
        raise AssertionError("must not be called")

    groundlens.set_default_encoder(encoder)
    try:
        assert _load_frozen_mu_hat(DEFAULT_MODEL, None, None) is None
    finally:
        groundlens.set_default_encoder(None)


def test_a_mismatched_hash_falls_back_rather_than_raising() -> None:
    """Degrade to the old behaviour, never to a wrong answer.

    No mocking: this corrupts the recorded hash on disk and restores it. The
    loader resolves package data at call time, so a patched module attribute
    would not be consulted and the test would pass without exercising anything.
    """
    meta_path = pathlib.Path(str(DATA / _FROZEN_META))
    original = meta_path.read_text(encoding="utf-8")
    try:
        bad = dict(_meta(), reference_pairs_sha256="0" * 64)
        meta_path.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        assert _load_frozen_mu_hat(DEFAULT_MODEL, None, None) is None, (
            "the loader used a direction whose CSV hash did not match"
        )
    finally:
        meta_path.write_text(original, encoding="utf-8")

    # and it recovers once the file is right again
    assert _load_frozen_mu_hat(DEFAULT_MODEL, None, None) is not None


def test_a_corrupt_npy_falls_back_rather_than_raising() -> None:
    """A truncated or unreadable array must not take down `import groundlens`."""
    npy_path = pathlib.Path(str(DATA / _FROZEN_MU_HAT))
    original = npy_path.read_bytes()
    try:
        npy_path.write_bytes(b"not a numpy array")
        assert _load_frozen_mu_hat(DEFAULT_MODEL, None, None) is None
    finally:
        npy_path.write_bytes(original)

    assert _load_frozen_mu_hat(DEFAULT_MODEL, None, None) is not None


def test_a_non_unit_vector_is_refused() -> None:
    """DGI is a cosine against this vector. Scale it and every score is wrong."""
    npy_path = pathlib.Path(str(DATA / _FROZEN_MU_HAT))
    original = npy_path.read_bytes()
    try:
        with npy_path.open("rb") as fh:
            mu = np.load(fh, allow_pickle=False)
        with npy_path.open("wb") as fh:
            np.save(fh, (mu * 2.0).astype(np.float32), allow_pickle=False)
        assert _load_frozen_mu_hat(DEFAULT_MODEL, None, None) is None
    finally:
        npy_path.write_bytes(original)
