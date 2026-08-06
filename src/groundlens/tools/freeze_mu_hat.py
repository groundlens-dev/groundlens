"""Regenerate the precomputed DGI reference direction that ships in the package.

    python -m groundlens.tools.freeze_mu_hat

Run this when, and only when, one of its two inputs changes on purpose: the
bundled ``reference_pairs.csv``, or the default encoder. Nothing else moves the
vector, because nothing else is an input to it.

Why the file exists at all: ``mu_hat`` is the mean of 212 unit displacement
vectors, a pure function of the CSV and the encoder. Deriving it means pushing
424 texts through ``sentence-t5-large`` -- 7m43s on a CI runner -- and that was
being paid on every CI run, every user's first DGI call, and every cold start of
the demo Space, to recompute a constant.

What the file is not: a replacement for checking the derivation.
``tests/integration/test_frozen_mu_hat.py`` derives it fresh with the real
encoder and asserts the shipped array matches to 1e-5. The claim that the
shipped direction comes from the shipped data is still proven -- once, in the
job built to pay for it, instead of on every machine that installs the package.

The companion JSON records the SHA-256 of the CSV it was fitted on. The loader
checks that hash at import time and falls back to deriving if it does not match,
so editing the CSV without rerunning this script degrades to the old behaviour
rather than scoring against a direction fitted on data that is no longer there.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import numpy as np

from groundlens._internal.csv_loader import load_reference_pairs
from groundlens._internal.embeddings import DEFAULT_MODEL
from groundlens.dgi import _FROZEN_META, _FROZEN_MU_HAT, _compute_reference_direction

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"


def main(data_dir: pathlib.Path | None = None) -> int:
    """Derive the direction with the real encoder and write it to package data.

    Args:
        data_dir: Where to write. Defaults to the installed package's ``data``
            directory, which is what you want when running this for real. Tests
            pass a temporary directory: this function overwrites a shipped
            artifact, so it must be possible to exercise it without doing that.

    Returns:
        ``0`` on success, ``1`` if an input is missing or the derived vector
        fails its sanity check.
    """
    data_dir = DATA if data_dir is None else data_dir
    csv_path = data_dir / "reference_pairs.csv"
    if not csv_path.exists():
        print(f"error: {csv_path} not found", file=sys.stderr)
        return 1

    pairs = load_reference_pairs()
    print(f"reference pairs      {len(pairs)}")
    print(f"encoder              {DEFAULT_MODEL}")
    print(f"texts to embed       {len(pairs) * 2}")
    print("deriving             this loads the encoder and takes several minutes...")

    mu = _compute_reference_direction(pairs, DEFAULT_MODEL)

    norm = float(np.linalg.norm(mu))
    if not np.isclose(norm, 1.0, atol=1e-5):
        print(f"error: derived vector is not unit norm ({norm})", file=sys.stderr)
        return 1

    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    meta = {
        "_comment": (
            "Precomputed DGI reference direction. Regenerate with "
            "`python -m groundlens.tools.freeze_mu_hat` when reference_pairs.csv "
            "or the default encoder changes on purpose, and never otherwise. "
            "The loader verifies reference_pairs_sha256 and falls back to "
            "deriving from the CSV if it does not match."
        ),
        "encoder": DEFAULT_MODEL,
        "dims": int(mu.shape[0]),
        "reference_pairs": len(pairs),
        "reference_pairs_sha256": digest,
        "dtype": str(mu.dtype),
    }

    data_dir.mkdir(parents=True, exist_ok=True)
    npy_path = data_dir / _FROZEN_MU_HAT
    with npy_path.open("wb") as fh:
        np.save(fh, mu, allow_pickle=False)
    (data_dir / _FROZEN_META).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"wrote                {npy_path.name}  ({npy_path.stat().st_size} bytes)")
    print(f"wrote                {_FROZEN_META}")
    print(f"dims                 {meta['dims']}")
    print(f"norm                 {norm:.8f}")
    print(f"csv sha256           {digest[:16]}...")
    print(f"first 4 components   {np.array2string(mu[:4], precision=6)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
