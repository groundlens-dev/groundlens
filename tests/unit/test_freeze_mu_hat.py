"""The generator that produces a shipped artifact needs its own tests.

`freeze_mu_hat` writes the `.npy` that every default-config DGI call reads and
the JSON hash that decides whether the loader trusts it. The expensive part —
424 texts through `sentence-t5-large` — cannot run here and does not need to:
`tests/integration/test_frozen_mu_hat.py` covers whether the derivation is
*right*. What is worth testing without an encoder is everything around it, and
that is most of the script:

* the metadata is built from the CSV that was actually read, not a stale copy,
* a derived vector that is not unit norm is refused rather than written,
* a missing CSV is an error rather than a traceback,
* what it writes is what the loader accepts.

That last one is the point. The generator and the loader are two halves of one
contract, written at the same time, and nothing else in the suite would notice
if they disagreed — a wrong hash in the metadata makes the loader silently fall
back to deriving, which looks exactly like everything working.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
from importlib.resources import files

import numpy as np
import pytest

from groundlens._internal.embeddings import DEFAULT_MODEL
from groundlens.dgi import _FROZEN_META, _FROZEN_MU_HAT
from groundlens.tools import freeze_mu_hat

REAL_CSV = pathlib.Path(str(files("groundlens.data") / "reference_pairs.csv"))


@pytest.fixture
def data_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """A throwaway package-data directory holding the real reference CSV."""
    d = tmp_path / "data"
    d.mkdir()
    shutil.copy(REAL_CSV, d / "reference_pairs.csv")
    return d


@pytest.fixture
def stub_derivation(monkeypatch: pytest.MonkeyPatch) -> np.ndarray:
    """Stand in for the encoder. Returns the unit vector it will 'derive'."""
    rng = np.random.default_rng(20260805)
    mu = rng.standard_normal(768).astype(np.float32)
    mu /= np.linalg.norm(mu)
    monkeypatch.setattr(
        freeze_mu_hat, "_compute_reference_direction", lambda *a, **k: mu, raising=True
    )
    return mu


def test_it_writes_both_files_and_succeeds(
    data_dir: pathlib.Path, stub_derivation: np.ndarray
) -> None:
    assert freeze_mu_hat.main(data_dir) == 0
    assert (data_dir / _FROZEN_MU_HAT).is_file()
    assert (data_dir / _FROZEN_META).is_file()


def test_the_vector_it_writes_is_the_vector_it_derived(
    data_dir: pathlib.Path, stub_derivation: np.ndarray
) -> None:
    freeze_mu_hat.main(data_dir)
    with (data_dir / _FROZEN_MU_HAT).open("rb") as fh:
        written = np.load(fh, allow_pickle=False)
    np.testing.assert_allclose(written, stub_derivation, atol=0)
    assert written.dtype == np.float32


def test_the_recorded_hash_is_of_the_csv_it_read(
    data_dir: pathlib.Path, stub_derivation: np.ndarray
) -> None:
    """The hash is the loader's only defence against a stale vector."""
    freeze_mu_hat.main(data_dir)
    meta = json.loads((data_dir / _FROZEN_META).read_text(encoding="utf-8"))
    assert meta["reference_pairs_sha256"] == hashlib.sha256(REAL_CSV.read_bytes()).hexdigest()


def test_the_metadata_describes_the_artifact(
    data_dir: pathlib.Path, stub_derivation: np.ndarray
) -> None:
    freeze_mu_hat.main(data_dir)
    meta = json.loads((data_dir / _FROZEN_META).read_text(encoding="utf-8"))
    assert meta["encoder"] == DEFAULT_MODEL
    assert meta["dims"] == 768
    assert meta["reference_pairs"] == 212
    assert meta["dtype"] == "float32"
    assert "freeze_mu_hat" in meta["_comment"], "the file should say how to regenerate it"


def test_a_missing_csv_is_an_error_not_a_traceback(tmp_path: pathlib.Path) -> None:
    assert freeze_mu_hat.main(tmp_path / "empty") == 1


def test_a_non_unit_vector_is_refused_and_nothing_is_written(
    data_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DGI is a cosine against this vector. Writing a scaled one poisons it.

    Refusing is not enough on its own — it has to refuse *before* writing, or
    the next run of the loader picks up a half-finished artifact.
    """
    monkeypatch.setattr(
        freeze_mu_hat,
        "_compute_reference_direction",
        lambda *a, **k: np.full(768, 0.5, dtype=np.float32),
        raising=True,
    )
    assert freeze_mu_hat.main(data_dir) == 1
    assert not (data_dir / _FROZEN_MU_HAT).exists(), "a rejected vector must not be written"
    assert not (data_dir / _FROZEN_META).exists()


def test_what_it_writes_is_what_the_loader_accepts(
    data_dir: pathlib.Path, stub_derivation: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generator and the loader are two halves of one contract.

    If they ever disagree the loader falls back to deriving, silently, and
    everything keeps working — slowly, and with nobody able to tell why.
    """
    import groundlens.dgi as dgi

    freeze_mu_hat.main(data_dir)

    class _Data:
        def __truediv__(self, name: str) -> pathlib.Path:
            return data_dir / name

    monkeypatch.setattr(dgi, "files", lambda _pkg: _Data(), raising=False)
    loaded = dgi._load_frozen_mu_hat(DEFAULT_MODEL, None, None)
    assert loaded is not None, "the loader rejected what the generator just wrote"
    np.testing.assert_allclose(loaded, stub_derivation, atol=0)
