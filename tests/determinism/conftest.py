"""Pytest hook-up for the determinism suite.

All the work is in ``_bootstrap``, which is a plain module rather
than a conftest so that ``export_golden.py`` — run by CI outside
pytest — can use the same import path setup.
"""

from __future__ import annotations

from . import _bootstrap as _bootstrap
