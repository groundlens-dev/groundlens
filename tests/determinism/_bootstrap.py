"""Import bootstrap for the determinism suite.

Make it runnable with nothing but pytest installed.

The suite is a binary gate on a control path that is standard library
only, so it has to be runnable from a bare checkout with no dependency
tree at all. Two obstacles, handled here in order:

1. ``groundlens`` may not be installed. Then ``src/`` goes on
   ``sys.path``.
2. ``groundlens/__init__.py`` still eagerly imports the geometry layer,
   which needs numpy and sentence-transformers. Importing
   ``groundlens.determinism`` would drag all of that in for no reason.
   When that import fails, a package shim is installed: a bare module
   object whose ``__path__`` points at ``src/groundlens`` and whose
   ``__init__.py`` is never executed, so the submodules load on their
   own.

The shim is not a workaround to be tidied away later. It is the reason
this job can prove the deterministic modules need nothing outside the
standard library: if one of them grows a third-party import, the gate
goes red on a runner where that package does not exist. Once
``__init__.py`` no longer pulls the geometry layer in, step 2 simply
stops firing.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_PKG = _SRC / "groundlens"


def _install_package_shim() -> None:
    """Register ``groundlens`` as a package without running its ``__init__``."""
    spec = ModuleSpec("groundlens", loader=None, is_package=True)
    spec.submodule_search_locations = [str(_PKG)]  # type: ignore[assignment]
    module = importlib.util.module_from_spec(spec)
    sys.modules["groundlens"] = module


def _bootstrap() -> None:
    if importlib.util.find_spec("groundlens") is None and _SRC.is_dir():
        sys.path.insert(0, str(_SRC))
    try:
        importlib.import_module("groundlens")
    except ImportError:
        sys.modules.pop("groundlens", None)
        _install_package_shim()


_bootstrap()
