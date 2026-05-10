"""Unit tests for groundlens.calibrate — CalibrationResult and calibrate().

All tests mock encode_texts / _compute_reference_direction so no
embedding model is loaded.

Note: ``groundlens.__init__`` re-exports ``calibrate`` as a function,
shadowing the module name.  We use ``patch.object`` on the explicitly
imported module to avoid the namespace collision.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path  # noqa: TC003
from unittest.mock import patch

import numpy as np
import pytest

import groundlens.calibrate  # noqa: F401

_cal_mod = sys.modules["groundlens.calibrate"]

from groundlens.calibrate import CalibrationResult, calibrate  # noqa: E402

# ---------------------------------------------------------------------------
# CalibrationResult save/load round-trip
# ---------------------------------------------------------------------------


class TestCalibrationResult:
    """Test CalibrationResult persistence."""

    def _make_result(self) -> CalibrationResult:
        return CalibrationResult(
            model="test-model",
            n_pairs=25,
            embedding_dim=384,
            mu_hat=np.array([0.1, 0.2, 0.3], dtype=np.float32),
            concentration=12.5,
            metadata={"domain": "legal"},
        )

    def test_save_creates_json_file(self, tmp_path: Path) -> None:
        result = self._make_result()
        out = tmp_path / "cal.json"
        result.save(out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["model"] == "test-model"
        assert data["n_pairs"] == 25
        assert data["concentration"] == 12.5

    def test_load_restores_fields(self, tmp_path: Path) -> None:
        original = self._make_result()
        out = tmp_path / "cal.json"
        original.save(out)

        loaded = CalibrationResult.load(out)
        assert loaded.model == original.model
        assert loaded.n_pairs == original.n_pairs
        assert loaded.embedding_dim == original.embedding_dim
        assert loaded.concentration == original.concentration
        assert loaded.metadata == original.metadata
        np.testing.assert_allclose(loaded.mu_hat, original.mu_hat, atol=1e-6)

    def test_load_missing_metadata_defaults_to_empty(self, tmp_path: Path) -> None:
        """Files saved without metadata should load gracefully."""
        data = {
            "model": "m",
            "n_pairs": 10,
            "embedding_dim": 3,
            "mu_hat": [0.1, 0.2, 0.3],
            "concentration": 5.0,
        }
        out = tmp_path / "no_meta.json"
        out.write_text(json.dumps(data))

        loaded = CalibrationResult.load(out)
        assert loaded.metadata == {}


# ---------------------------------------------------------------------------
# calibrate() validation
# ---------------------------------------------------------------------------

_FAKE_MU = np.array([1.0, 0.0, 0.0], dtype=np.float32)


class TestCalibrateValidation:
    """Test input validation in calibrate()."""

    def test_neither_pairs_nor_csv_raises(self) -> None:
        with pytest.raises(ValueError, match="Provide either"):
            calibrate()

    def test_too_few_pairs_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 5 pairs"):
            calibrate(pairs=[("Q?", "A.") for _ in range(3)])

    @patch.object(_cal_mod, "_compute_reference_direction", return_value=_FAKE_MU)
    @patch("groundlens._internal.embeddings.encode_texts")
    def test_happy_path_returns_result(
        self,
        mock_encode,
        mock_ref_dir,
    ) -> None:
        rng = np.random.default_rng(0)
        # 10 pairs → 20 texts
        mock_encode.return_value = rng.standard_normal((20, 3)).astype(np.float32)

        result = calibrate(pairs=[("Q?", "A.") for _ in range(10)])
        assert result.n_pairs == 10
        assert result.embedding_dim == 3
        assert result.concentration > 0
        np.testing.assert_array_equal(result.mu_hat, _FAKE_MU)

    @patch.object(_cal_mod, "_compute_reference_direction", return_value=_FAKE_MU)
    @patch("groundlens._internal.embeddings.encode_texts")
    def test_metadata_stored(
        self,
        mock_encode,
        mock_ref_dir,
    ) -> None:
        rng = np.random.default_rng(1)
        mock_encode.return_value = rng.standard_normal((10, 3)).astype(np.float32)

        result = calibrate(
            pairs=[("Q?", "A.") for _ in range(5)],
            metadata={"domain": "medical"},
        )
        assert result.metadata == {"domain": "medical"}

    @patch("groundlens._internal.csv_loader.load_reference_pairs")
    @patch.object(_cal_mod, "_compute_reference_direction", return_value=_FAKE_MU)
    @patch("groundlens._internal.embeddings.encode_texts")
    def test_csv_path_loads_pairs(
        self,
        mock_encode,
        mock_ref_dir,
        mock_loader,
    ) -> None:
        pairs = [("Q?", "A.") for _ in range(10)]
        mock_loader.return_value = pairs
        rng = np.random.default_rng(2)
        mock_encode.return_value = rng.standard_normal((20, 3)).astype(np.float32)

        result = calibrate(csv_path="domain.csv")
        mock_loader.assert_called_once_with("domain.csv")
        assert result.n_pairs == 10
