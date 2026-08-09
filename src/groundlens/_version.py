"""Groundlens version — SemVer format MAJOR.MINOR.PATCH.

2.0.0 replaces the CalVer scheme (``YYYY.M.D``) used up to ``2026.8.5``. The
control path has a public contract now — finding codes, the audit record
schema, the pack format — and callers need a version number that tells them
when that contract breaks. A date cannot do that.

Single source of truth is ``[project].version`` in ``pyproject.toml``. This
module reads the installed distribution metadata so ``groundlens.__version__``,
``groundlens --version`` and the built wheel can never disagree. The literal
below is only a fallback for running from a source tree that was never
installed; keep it in step with pyproject.toml when you cut a release.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

_FALLBACK = "2.0.0"

try:
    __version__: str = _dist_version("groundlens")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = _FALLBACK
