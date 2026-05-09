"""Tests for groundlens._internal.geometry functions."""

from __future__ import annotations

import numpy as np
import pytest

from groundlens._internal.geometry import (
    cosine_similarity,
    displacement_vector,
    euclidean_distance,
    mean_direction,
    unit_normalize,
)

# ---------------------------------------------------------------------------
# euclidean_distance
# ---------------------------------------------------------------------------


class TestEuclideanDistance:
    """Tests for euclidean_distance()."""

    def test_identical_vectors_return_zero(self) -> None:
        v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert euclidean_distance(v, v) == pytest.approx(0.0)

    def test_known_distance(self) -> None:
        a = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([3.0, 4.0, 0.0], dtype=np.float32)
        assert euclidean_distance(a, b) == pytest.approx(5.0)

    def test_unit_vectors_along_axes(self) -> None:
        e1 = np.array([1.0, 0.0], dtype=np.float32)
        e2 = np.array([0.0, 1.0], dtype=np.float32)
        assert euclidean_distance(e1, e2) == pytest.approx(np.sqrt(2.0))

    def test_symmetry(self) -> None:
        rng = np.random.default_rng(0)
        a = rng.standard_normal(128).astype(np.float32)
        b = rng.standard_normal(128).astype(np.float32)
        assert euclidean_distance(a, b) == pytest.approx(euclidean_distance(b, a))

    def test_non_negative(self) -> None:
        rng = np.random.default_rng(1)
        a = rng.standard_normal(64).astype(np.float32)
        b = rng.standard_normal(64).astype(np.float32)
        assert euclidean_distance(a, b) >= 0.0

    def test_zero_vectors(self) -> None:
        z = np.zeros(10, dtype=np.float32)
        assert euclidean_distance(z, z) == pytest.approx(0.0)

    def test_high_dimensional(self) -> None:
        rng = np.random.default_rng(2)
        a = rng.standard_normal(384).astype(np.float32)
        b = rng.standard_normal(384).astype(np.float32)
        result = euclidean_distance(a, b)
        expected = float(np.linalg.norm(a - b))
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# unit_normalize
# ---------------------------------------------------------------------------


class TestUnitNormalize:
    """Tests for unit_normalize()."""

    def test_unit_vector_unchanged(self) -> None:
        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        result = unit_normalize(v)
        np.testing.assert_allclose(result, v, atol=1e-7)

    def test_output_has_unit_norm(self) -> None:
        v = np.array([3.0, 4.0], dtype=np.float32)
        result = unit_normalize(v)
        assert float(np.linalg.norm(result)) == pytest.approx(1.0, abs=1e-6)

    def test_direction_preserved(self) -> None:
        v = np.array([2.0, 0.0, 0.0], dtype=np.float32)
        result = unit_normalize(v)
        np.testing.assert_allclose(result, [1.0, 0.0, 0.0], atol=1e-7)

    def test_zero_vector_returns_zero(self) -> None:
        z = np.zeros(5, dtype=np.float32)
        result = unit_normalize(z)
        np.testing.assert_allclose(result, z, atol=1e-9)

    def test_near_zero_vector_returns_as_is(self) -> None:
        v = np.array([1e-10, 0.0, 0.0], dtype=np.float32)
        result = unit_normalize(v)
        # Near-zero vectors should be returned unchanged
        np.testing.assert_allclose(result, v, atol=1e-9)

    def test_negative_components(self) -> None:
        v = np.array([-3.0, -4.0], dtype=np.float32)
        result = unit_normalize(v)
        assert float(np.linalg.norm(result)) == pytest.approx(1.0, abs=1e-6)
        assert result[0] < 0
        assert result[1] < 0

    def test_high_dimensional(self) -> None:
        rng = np.random.default_rng(3)
        v = rng.standard_normal(384).astype(np.float32)
        result = unit_normalize(v)
        assert float(np.linalg.norm(result)) == pytest.approx(1.0, abs=1e-5)


# ---------------------------------------------------------------------------
# displacement_vector
# ---------------------------------------------------------------------------


class TestDisplacementVector:
    """Tests for displacement_vector()."""

    def test_basic_displacement(self) -> None:
        q = np.array([1.0, 0.0], dtype=np.float32)
        r = np.array([3.0, 2.0], dtype=np.float32)
        result = displacement_vector(q, r)
        np.testing.assert_allclose(result, [2.0, 2.0])

    def test_identical_vectors_give_zero(self) -> None:
        v = np.array([5.0, 5.0, 5.0], dtype=np.float32)
        result = displacement_vector(v, v)
        np.testing.assert_allclose(result, np.zeros(3))

    def test_anti_symmetric(self) -> None:
        q = np.array([1.0, 2.0], dtype=np.float32)
        r = np.array([3.0, 4.0], dtype=np.float32)
        d_qr = displacement_vector(q, r)
        d_rq = displacement_vector(r, q)
        np.testing.assert_allclose(d_qr, -d_rq)

    def test_zero_question(self) -> None:
        q = np.zeros(3, dtype=np.float32)
        r = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        result = displacement_vector(q, r)
        np.testing.assert_allclose(result, r)


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    """Tests for cosine_similarity()."""

    def test_identical_vectors_return_one(self) -> None:
        v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors_return_zero(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors_return_negative_one(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        assert cosine_similarity(a, b) == pytest.approx(-1.0, abs=1e-6)

    def test_zero_vector_a_returns_zero(self) -> None:
        z = np.zeros(3, dtype=np.float32)
        v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert cosine_similarity(z, v) == pytest.approx(0.0)

    def test_zero_vector_b_returns_zero(self) -> None:
        v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        z = np.zeros(3, dtype=np.float32)
        assert cosine_similarity(v, z) == pytest.approx(0.0)

    def test_both_zero_vectors(self) -> None:
        z = np.zeros(3, dtype=np.float32)
        assert cosine_similarity(z, z) == pytest.approx(0.0)

    def test_scale_invariance(self) -> None:
        v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert cosine_similarity(v, 100 * v) == pytest.approx(1.0, abs=1e-6)

    def test_known_angle(self) -> None:
        # 45-degree angle in 2D
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([1.0, 1.0], dtype=np.float32)
        expected = np.cos(np.pi / 4)
        assert cosine_similarity(a, b) == pytest.approx(expected, abs=1e-5)

    def test_range_bounded(self) -> None:
        rng = np.random.default_rng(4)
        for _ in range(50):
            a = rng.standard_normal(64).astype(np.float32)
            b = rng.standard_normal(64).astype(np.float32)
            sim = cosine_similarity(a, b)
            assert -1.0 - 1e-6 <= sim <= 1.0 + 1e-6


# ---------------------------------------------------------------------------
# mean_direction
# ---------------------------------------------------------------------------


class TestMeanDirection:
    """Tests for mean_direction()."""

    def test_single_vector(self) -> None:
        v = unit_normalize(np.array([1.0, 1.0, 0.0], dtype=np.float32))
        result = mean_direction([v])
        np.testing.assert_allclose(result, v, atol=1e-6)

    def test_same_direction_vectors(self) -> None:
        v = unit_normalize(np.array([1.0, 0.0, 0.0], dtype=np.float32))
        result = mean_direction([v, v, v])
        np.testing.assert_allclose(result, v, atol=1e-6)

    def test_output_is_unit_length(self) -> None:
        rng = np.random.default_rng(5)
        vecs = [unit_normalize(rng.standard_normal(64).astype(np.float32)) for _ in range(10)]
        result = mean_direction(vecs)
        assert float(np.linalg.norm(result)) == pytest.approx(1.0, abs=1e-5)

    def test_opposing_vectors_cancel(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        result = mean_direction([a, b])
        # Mean of opposing unit vectors is zero; unit_normalize returns zero
        assert float(np.linalg.norm(result)) < 1e-6

    def test_empty_list_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            mean_direction([])

    def test_two_orthogonal_vectors(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        result = mean_direction([a, b])
        expected = unit_normalize(np.array([1.0, 1.0], dtype=np.float32))
        np.testing.assert_allclose(result, expected, atol=1e-6)
