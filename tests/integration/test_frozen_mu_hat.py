"""The shipped direction must equal one derived from the shipped CSV.

This is the test that keeps the audit claim true. The package no longer derives
``mu_hat`` at runtime — it loads a 3 KB array — so *something* has to prove that
array is what the reference corpus and the default encoder actually produce.
This is that something, and it is the only place that pays for it: 424 texts
through ``sentence-t5-large``, about eight minutes.

Before, every process paid that cost to reach the same answer: CI on every run,
every user on their first DGI call, the demo Space on every cold start. Now one
CI job pays it and everyone else reads the result.

If this fails, do not regenerate the file to make it pass. A mismatch means one
of the two inputs moved — the CSV or the default encoder — and which one it was
is the finding. Regenerating first destroys the evidence.
"""

from __future__ import annotations

import json
from importlib.resources import files

import numpy as np
import pytest

from groundlens._internal.csv_loader import load_reference_pairs
from groundlens._internal.embeddings import DEFAULT_MODEL
from groundlens.dgi import (
    _FROZEN_META,
    _FROZEN_MU_HAT,
    _compute_reference_direction,
    _load_frozen_mu_hat,
)

pytestmark = pytest.mark.slow

DATA = files("groundlens.data")

#: Tight. The two vectors come from the same arithmetic on the same inputs, so
#: the only slack needed is CPU/BLAS reduction order.
ATOL = 1e-5


@pytest.fixture(scope="module")
def derived() -> np.ndarray:
    """Derive the direction once for this module. This is the expensive part."""
    return _compute_reference_direction(load_reference_pairs(), DEFAULT_MODEL)


@pytest.fixture(scope="module")
def frozen() -> np.ndarray:
    mu = _load_frozen_mu_hat(DEFAULT_MODEL, None, None)
    assert mu is not None, "the shipped direction did not load; see the unit contract tests"
    return mu


def test_the_shipped_direction_is_what_the_csv_produces(
    frozen: np.ndarray, derived: np.ndarray
) -> None:
    """Component-wise. A mean of 212 unit vectors has no room for drift."""
    assert frozen.shape == derived.shape
    np.testing.assert_allclose(frozen, derived, atol=ATOL, err_msg=_HELP)


def test_the_two_agree_on_every_direction_they_score(
    frozen: np.ndarray, derived: np.ndarray
) -> None:
    """The number DGI reports is a cosine against this vector.

    Component equality already implies this, but the cosine is what users see,
    so assert it in the units the failure would reach them in.
    """
    cosine = float(np.dot(frozen, derived))
    assert cosine == pytest.approx(1.0, abs=ATOL), (
        f"shipped and derived directions differ by {np.degrees(np.arccos(min(cosine, 1.0))):.4f} "
        f"degrees. Every DGI score in the package is a cosine against this vector.\n{_HELP}"
    )


def test_the_metadata_describes_what_was_actually_derived(derived: np.ndarray) -> None:
    """dims and pair count are cheap to record and cheap to get wrong."""
    meta = json.loads((DATA / _FROZEN_META).read_text(encoding="utf-8"))
    assert meta["dims"] == derived.shape[0]
    assert meta["reference_pairs"] == len(load_reference_pairs())
    assert meta["encoder"] == DEFAULT_MODEL


_HELP = (
    f"\n{_FROZEN_MU_HAT} does not match a fresh derivation from "
    "reference_pairs.csv.\n"
    "Do NOT regenerate to make this pass. A mismatch means one of the two "
    "inputs moved:\n"
    "  - reference_pairs.csv changed (the unit contract test checks its "
    "sha256 and would also be red), or\n"
    "  - the default encoder changed, or its weights did.\n"
    "Find out which before regenerating, because regenerating destroys the "
    "evidence.\n"
    "When it is deliberate: python -m groundlens.tools.freeze_mu_hat"
)
