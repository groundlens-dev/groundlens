"""Golden regression: real encoder, real scores, fixed expected values.

These are the tests that would have caught both silent default-encoder
changes. Everything else in the suite either mocks the embedding layer or
asserts a property (a range, a sign, an ordering) that survives swapping the
encoder underneath it. These do not: they pin a *number*.

They are marked ``slow`` because they download and run
``sentence-transformers/sentence-t5-large`` (~640 MB, CPU is fine). CI runs
them in a dedicated job with the HuggingFace cache restored; ``pytest -m "not
slow"`` skips them.

Regenerating the constants
--------------------------
Only ever regenerate these because the encoder default *intentionally*
changed, and say so in the changelog::

    pytest tests/integration/test_golden_scores.py --regenerate-golden

A diff in these values with no deliberate change to the default encoder means
something moved that was not supposed to move.
"""

from __future__ import annotations

import numpy as np
import pytest

from groundlens._internal.embeddings import DEFAULT_MODEL, get_default_encoder
from groundlens._internal.thresholds import DGI_PASS, SGI_REVIEW, SGI_STRONG_PASS
from groundlens.dgi import compute_dgi, reset_calibration_cache
from groundlens.sgi import compute_sgi

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module", autouse=True)
def _calibrated_once() -> object:
    """Compute the DGI reference direction once for the whole module.

    ``mu_hat`` is a pure function of the shipped reference CSV and the active
    encoder, and ``_get_mu_hat`` already keys its cache on both -- a custom
    encoder or a custom CSV gets its own entry and can never read a stale
    bundled direction. So clearing the cache inside a test protects against
    nothing, and it costs a full re-embed of all 212 reference pairs: 424
    texts through sentence-t5-large.

    That is not a small cost. Measured on the ubuntu-latest runner, a single
    recalibration takes **7 minutes 43 seconds**. This file used to call
    ``reset_calibration_cache()`` at the top of eight separate tests, so the
    job needed 62 minutes of recomputation to finish and had a 30-minute
    timeout. It never finished. It reported ``The operation was canceled``
    partway through the DGI class on every single run, which reads as
    infrastructure flakiness rather than as the deterministic arithmetic it
    actually was.

    The tell is in the log: ``test_flag_boundary_is_dgi_pass_and_nothing_else``
    is the one DGI test that never called the reset, and it took 1.8 seconds
    against 463 for each of its neighbours.

    One reset here, before the first test, and one after the last so the
    module leaves no cached state behind for anything that runs after it.
    """
    reset_calibration_cache()
    yield
    reset_calibration_cache()


# Tolerance. Tight enough that an encoder swap fails, loose enough to absorb
# CPU/BLAS non-determinism and minor torch/sentence-transformers releases.
ATOL = 0.02

# ── The golden triple ────────────────────────────────────────────────────────
# Deliberately NOT drawn from src/groundlens/data/reference_pairs.csv: that
# file defines mu_hat and the Youden cut, so anything in it is scored on its
# own calibration data.
GOLDEN_QUESTION = (
    "How long does the Northwind warehouse keep a returned item before it is "
    "restocked, and who signs off on the inspection?"
)
GOLDEN_CONTEXT = (
    "Returned items arrive at the Northwind warehouse dock and enter a 14-day "
    "quarantine bay. During quarantine a floor supervisor inspects the item "
    "against the original packing slip. Only after the supervisor signs the "
    "inspection line does the item move to restocking; unsigned items are held "
    "past 14 days and escalated to the regional manager."
)
GOLDEN_GROUNDED = (
    "A returned item sits in the quarantine bay for 14 days. A floor supervisor "
    "checks it against the original packing slip and signs the inspection line; "
    "only then is it restocked. If nobody signs, it is held beyond the 14 days "
    "and goes to the regional manager."
)
GOLDEN_UNGROUNDED = (
    "Northwind restocks returned items the same afternoon they arrive, with no "
    "quarantine period at all. Inspection is fully automated, so no member of "
    "staff signs anything, and the regional manager is never involved."
)

# ── A second pair, freshly written, in a domain the reference set covers ─────
# Measured 2026-08-04 on sentence-t5-large:
#
#   the 212 grounded reference responses   0.2536 .. 0.7609, median 0.5569
#   warehouse logistics, grounded          0.1235
#   this medical pair, grounded            0.2177
#   DGI_PASS                               0.5250
#
# Medical is one of the nine domains in reference_pairs.csv (40 of 212 rows),
# so the first theory - that the warehouse pair simply sat outside the covered
# domains - is disproved by this pair scoring just as low.
#
# What separates them is not topic, it is authorship. Every one of the 212
# grounded responses was generated by Claude Sonnet 4.5 answering a textbook
# question. mu_hat is the mean of their displacement directions, so what it
# encodes is that register. Text written any other way displaces elsewhere and
# scores in the low 0.1-0.2 band however faithfully it tracks its source.
#
# Both pairs are pinned. Read them together: they are the evidence that
# DGI_PASS is a property of the calibration corpus rather than of grounding.
FRESH_QUESTION = "Why does a doctor check ferritin when someone reports being tired all the time?"
FRESH_GROUNDED = (
    "Ferritin is the protein that stores iron, so the level in blood reflects how much "
    "iron the body is holding in reserve. A low result points to depleted stores, and "
    "those stores run down before the blood count itself drops, so ferritin can show a "
    "problem earlier than a standard full blood count would. That is why it is measured "
    "early when someone reports persistent tiredness."
)
FRESH_UNGROUNDED = (
    "Ferritin measures how fast red blood cells move through the smaller vessels, and a "
    "doctor checks it because circulation speed is the main thing that sets daytime "
    "energy. A high ferritin reading means the blood is moving too quickly, which tires "
    "the muscles out and produces the slump most people feel by mid afternoon."
)


class TestGoldenSGI:
    """A fixed (question, context, response) triple must score a fixed value."""

    def test_default_model_is_what_the_thresholds_were_calibrated_on(self) -> None:
        assert DEFAULT_MODEL == "sentence-transformers/sentence-t5-large"

    def test_no_process_global_encoder_is_leaking_into_this_test(self) -> None:
        assert get_default_encoder() is None

    def test_encoder_width(self) -> None:
        from groundlens._internal.embeddings import encode_texts

        assert encode_texts(["dimension probe"]).shape[1] == 768

    def test_grounded_triple_scores_the_golden_value(
        self, golden_values: dict[str, float]
    ) -> None:
        result = compute_sgi(
            question=GOLDEN_QUESTION,
            context=GOLDEN_CONTEXT,
            response=GOLDEN_GROUNDED,
        )
        assert result.value == pytest.approx(golden_values["sgi_grounded"], abs=ATOL)
        assert result.flagged is False
        assert result.value >= SGI_STRONG_PASS

    def test_ungrounded_triple_scores_the_golden_value(
        self, golden_values: dict[str, float]
    ) -> None:
        result = compute_sgi(
            question=GOLDEN_QUESTION,
            context=GOLDEN_CONTEXT,
            response=GOLDEN_UNGROUNDED,
        )
        assert result.value == pytest.approx(golden_values["sgi_ungrounded"], abs=ATOL)

    def test_grounded_outscores_ungrounded(self) -> None:
        grounded = compute_sgi(
            question=GOLDEN_QUESTION, context=GOLDEN_CONTEXT, response=GOLDEN_GROUNDED
        )
        ungrounded = compute_sgi(
            question=GOLDEN_QUESTION, context=GOLDEN_CONTEXT, response=GOLDEN_UNGROUNDED
        )
        assert grounded.value > ungrounded.value

    def test_angular_distances_are_radians_not_euclidean_norms(self) -> None:
        """q_dist / ctx_dist are arccos values, so both live in [0, pi]."""
        result = compute_sgi(
            question=GOLDEN_QUESTION, context=GOLDEN_CONTEXT, response=GOLDEN_GROUNDED
        )
        assert 0.0 <= result.q_dist <= np.pi
        assert 0.0 <= result.ctx_dist <= np.pi

    def test_scoring_is_deterministic(self) -> None:
        first = compute_sgi(
            question=GOLDEN_QUESTION, context=GOLDEN_CONTEXT, response=GOLDEN_GROUNDED
        )
        second = compute_sgi(
            question=GOLDEN_QUESTION, context=GOLDEN_CONTEXT, response=GOLDEN_GROUNDED
        )
        assert first.value == second.value


class TestGoldenDGI:
    """The bundled mu_hat must reproduce from the shipped CSV, to a fixed value."""

    def test_grounded_pair_scores_the_golden_value(self, golden_values: dict[str, float]) -> None:
        result = compute_dgi(question=GOLDEN_QUESTION, response=GOLDEN_GROUNDED)
        assert result.value == pytest.approx(golden_values["dgi_grounded"], abs=ATOL)

    def test_ungrounded_pair_scores_the_golden_value(
        self, golden_values: dict[str, float]
    ) -> None:
        result = compute_dgi(question=GOLDEN_QUESTION, response=GOLDEN_UNGROUNDED)
        assert result.value == pytest.approx(golden_values["dgi_ungrounded"], abs=ATOL)

    def test_flag_boundary_is_dgi_pass_and_nothing_else(self) -> None:
        result = compute_dgi(question=GOLDEN_QUESTION, response=GOLDEN_GROUNDED)
        assert result.flagged == (result.value < DGI_PASS)

    def test_fresh_grounded_scores_the_golden_value(self, golden_values: dict[str, float]) -> None:
        result = compute_dgi(question=FRESH_QUESTION, response=FRESH_GROUNDED)
        assert result.value == pytest.approx(golden_values["dgi_fresh_grounded"], abs=ATOL)

    def test_fresh_ungrounded_scores_the_golden_value(
        self, golden_values: dict[str, float]
    ) -> None:
        result = compute_dgi(question=FRESH_QUESTION, response=FRESH_UNGROUNDED)
        assert result.value == pytest.approx(golden_values["dgi_fresh_ungrounded"], abs=ATOL)

    def test_freshly_written_grounded_text_does_not_clear_the_cut(self) -> None:
        """A known limitation, asserted so that fixing it is a visible event.

        This test asserts a defect, not a feature. Both freshly written
        grounded answers in this file score far below DGI_PASS - warehouse
        0.1235, medical 0.2177, against a cut of 0.525 - while the 212
        calibration responses run 0.2536 to 0.7609 with a median of 0.5569.
        Medical is one of the nine domains the calibration set covers, so
        topic does not explain the gap. Authorship does: every calibration
        response was generated by one model in one style, and mu_hat is the
        mean of their displacements.

        What this means for anyone using the library: with the bundled
        mu_hat, DGI flags grounded text that was not written in that register.
        Prefer SGI where a source is available, or recalibrate mu_hat on your
        own grounded corpus with groundlens.calibrate().

        When mu_hat is recalibrated on a broader corpus this test will fail.
        That failure is the point. It means the limitation is gone, and the
        test should then be inverted deliberately, in a commit that says so.
        """
        fresh = compute_dgi(question=FRESH_QUESTION, response=FRESH_GROUNDED)
        assert fresh.value < DGI_PASS
        assert fresh.flagged is True

    def test_fresh_grounded_outscores_fresh_ungrounded(self) -> None:
        grounded = compute_dgi(question=FRESH_QUESTION, response=FRESH_GROUNDED)
        ungrounded = compute_dgi(question=FRESH_QUESTION, response=FRESH_UNGROUNDED)
        assert grounded.value > ungrounded.value

    def test_both_fresh_grounded_answers_land_in_the_same_low_band(self) -> None:
        """Two fresh grounded answers, two unrelated domains, both far below.

        This is what rules out the domain explanation. Warehouse logistics is
        not a domain the calibration set covers; medical is 40 of its 212
        rows. They score 0.1235 and 0.2177. If coverage were the mechanism,
        the medical pair would land near the calibration median of 0.5569.
        """
        medical = compute_dgi(question=FRESH_QUESTION, response=FRESH_GROUNDED).value
        warehouse = compute_dgi(question=GOLDEN_QUESTION, response=GOLDEN_GROUNDED).value
        assert medical < DGI_PASS
        assert warehouse < DGI_PASS
        assert abs(medical - warehouse) < 0.25

    def test_mu_hat_is_a_unit_vector_of_the_encoder_width(self) -> None:
        from groundlens.dgi import _get_mu_hat

        mu = _get_mu_hat()
        assert mu.shape == (768,)
        assert float(np.linalg.norm(mu)) == pytest.approx(1.0, abs=1e-5)

    def test_bundled_reference_set_size(self) -> None:
        from groundlens._internal.csv_loader import load_reference_pairs

        assert len(load_reference_pairs()) == 212


class TestGoldenThresholds:
    """The constants the golden values are read against."""

    def test_thresholds_are_the_documented_values(self) -> None:
        assert SGI_STRONG_PASS == 1.20
        assert SGI_REVIEW == 0.95
        assert DGI_PASS == 0.525


class TestGoldenJobStaysAffordable:
    """Guards on the cost of this file, not on the numbers in it.

    This job loads the real encoder, so it is the one place in the suite where
    a careless line costs eight minutes instead of eight milliseconds. It went
    unnoticed for as long as it did because the failure surfaced as ``The
    operation was canceled`` -- a message that reads as a runner problem and
    sends you to look at the infrastructure rather than at the test file.
    """

    def test_the_reference_direction_is_computed_at_most_once(self) -> None:
        """No test may clear the calibration cache. The fixture owns that.

        A clear used to cost a re-embed of 424 texts through sentence-t5-large:
        7m43s on the CI runner. Eight of them exceeded the job timeout, so the
        job could not pass at any timeout under about 65 minutes.

        The bundled direction now ships precomputed, so a clear followed by a
        default-config score is cheap. It is not cheap for a custom encoder or a
        user CSV, which still derive, and it is not free even here: the point of
        the fixture is that this file's cost stays bounded no matter which of
        those a future test reaches for.

        If you need a cleared cache for something, use a custom
        ``reference_csv`` or a stub ``encoder``. ``_get_mu_hat`` keys its cache
        on both, so either gets you a fresh direction for free.
        """
        import ast
        import pathlib

        tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
        offenders = [
            f"{fn.name}:{call.lineno}"
            for fn in ast.walk(tree)
            if isinstance(fn, ast.FunctionDef) and fn.name.startswith("test_")
            for call in ast.walk(fn)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "reset_calibration_cache"
        ]
        assert not offenders, (
            f"reset_calibration_cache() called inside test(s): {offenders}. "
            "For any configuration that is not the bundled default this costs a "
            "full re-embed of 424 texts, 7m43s on the CI runner. The module "
            "fixture _calibrated_once already resets before the first test and "
            "after the last."
        )

    def test_a_second_call_hits_the_cache_rather_than_recomputing(self) -> None:
        """Same key, same array object. This is what makes one reset enough."""
        from groundlens.dgi import _get_mu_hat

        assert _get_mu_hat() is _get_mu_hat()
