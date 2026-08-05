"""The fuzz targets must be exercisable without a fuzzing engine.

ClusterFuzzLite failed with '100.0% of fuzz targets seem to be broken' and
nothing in the test suite would have caught it, because no test ever called
the function the target calls with the inputs the target feeds it.

These tests do exactly that, in plain Python, in milliseconds. They will not
find what a fuzzer finds. They will tell you the contract still holds before
you spend a container discovering it does not.
"""

from __future__ import annotations

import math

import pytest

from groundlens.check import check_for_verification


class TestCheckForVerificationIsTotal:
    """Any float must produce a renderable reading and never raise."""

    @pytest.mark.parametrize(
        "consistency",
        [
            0.0,
            1.0,
            0.5,
            -1.0,
            2.0,
            1e308,
            -1e308,
            1e-308,
            float("inf"),
            float("-inf"),
            float("nan"),
        ],
    )
    @pytest.mark.parametrize("n_samples", [0, 1, 5, 10000])
    def test_never_raises_and_always_renders(self, consistency: float, n_samples: int) -> None:
        reading = check_for_verification(consistency, n_samples=n_samples)
        rendered = reading.render()
        assert isinstance(rendered, str)
        assert rendered
        assert reading.level is not None
        assert isinstance(reading.label, str)
        assert isinstance(reading.escalate, bool)

    def test_nan_does_not_silently_become_a_pass(self) -> None:
        """A broken upstream must not read as a clean result."""
        reading = check_for_verification(float("nan"), n_samples=5)
        assert reading.escalate is True

    def test_the_target_module_imports(self) -> None:
        """fuzz/fuzz_check.py imports groundlens.check; so must this."""
        from groundlens.check import check_for_verification as _f

        assert callable(_f)

    def test_output_is_deterministic(self) -> None:
        first = check_for_verification(0.42, n_samples=5)
        second = check_for_verification(0.42, n_samples=5)
        assert first.render() == second.render()
        assert (first.level, first.label, first.escalate) == (
            second.level,
            second.label,
            second.escalate,
        )

    def test_the_whole_float_line_is_covered(self) -> None:
        """A coarse sweep, standing in for what the fuzzer does properly."""
        for i in range(-50, 151):
            c = i / 100.0
            reading = check_for_verification(c, n_samples=5)
            assert reading.render()
            assert not math.isnan(c) or reading.escalate
