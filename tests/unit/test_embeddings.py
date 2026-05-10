"""Unit tests for groundlens._internal.embeddings — caching and encoding."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

import groundlens._internal.embeddings as emb_mod


class TestResetCache:
    """Test reset_cache clears module-level state."""

    def test_clears_encoder(self) -> None:
        emb_mod._encoder = MagicMock()
        emb_mod._encoder_model_name = "test-model"

        emb_mod.reset_cache()
        assert emb_mod._encoder is None
        assert emb_mod._encoder_model_name is None


class TestGetEncoder:
    """Test get_encoder with mocked SentenceTransformer."""

    def setup_method(self) -> None:
        emb_mod.reset_cache()

    def teardown_method(self) -> None:
        emb_mod.reset_cache()

    @patch("groundlens._internal.embeddings.SentenceTransformer", create=True)
    def test_loads_model_on_first_call(self, mock_st_cls) -> None:
        fake_encoder = MagicMock()
        mock_st_cls.return_value = fake_encoder

        # Patch the import inside get_encoder
        fake_st_mod = MagicMock(SentenceTransformer=mock_st_cls)
        with patch.dict("sys.modules", {"sentence_transformers": fake_st_mod}):
            result = emb_mod.get_encoder("test-model")

        assert result is fake_encoder

    def test_returns_cached_encoder(self) -> None:
        fake = MagicMock()
        emb_mod._encoder = fake
        emb_mod._encoder_model_name = "cached-model"

        result = emb_mod.get_encoder("cached-model")
        assert result is fake


class TestEncodeTexts:
    """Test encode_texts with a mocked encoder."""

    def setup_method(self) -> None:
        emb_mod.reset_cache()

    def teardown_method(self) -> None:
        emb_mod.reset_cache()

    def test_calls_encoder(self) -> None:
        fake_encoder = MagicMock()
        expected = np.random.default_rng(0).standard_normal((2, 384)).astype(np.float32)
        fake_encoder.encode.return_value = expected

        emb_mod._encoder = fake_encoder
        emb_mod._encoder_model_name = "test-model"

        result = emb_mod.encode_texts(["hello", "world"], model_name="test-model")
        np.testing.assert_array_equal(result, expected)
        fake_encoder.encode.assert_called_once()
