"""Shared helpers for the determinism suite."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]

_CODE = (
    "import _bootstrap;"
    "from _sample import build_sample_record;"
    "from groundlens.audit_record import record_sha256;"
    "print(record_sha256(build_sample_record()))"
)


def record_digest_in_subprocess(env_overrides: dict[str, str]) -> str:
    """Rebuild the sample record in a fresh interpreter and return its digest.

    A fresh process is the only way to test things that are fixed at
    interpreter start: ``PYTHONHASHSEED`` and the environment the C
    locale is read from. ``_bootstrap`` is imported first so the child
    resolves ``groundlens`` the same way the suite does, with no
    dependency tree required.

    Args:
        env_overrides: Environment variables to set on top of the
            current environment.

    Returns:
        The hex digest the child printed.
    """
    env = dict(os.environ)
    env.update(env_overrides)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_HERE), str(_REPO / "src"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    out = subprocess.run(
        [sys.executable, "-c", _CODE],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO),
    )
    return out.stdout.strip()
