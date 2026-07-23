"""The invariant that protects the library's promise: no model in the core path.

`import groundlens` must not import torch, transformers, or sentence-transformers.
Neither must `import groundlens.verify`; the heavy libraries load only when a
detector actually runs. Each import is checked in a fresh subprocess so other
tests cannot pollute sys.modules.
"""

from __future__ import annotations

import subprocess
import sys

HEAVY = ("torch", "transformers", "sentence_transformers")


def _top_level_modules(import_line: str) -> set[str]:
    code = (
        "import sys\n"
        f"{import_line}\n"
        "print(','.join(sorted({m.split('.')[0] for m in sys.modules})))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    return set(out.stdout.strip().split(","))


def test_core_import_loads_no_heavy_libs() -> None:
    mods = _top_level_modules("import groundlens")
    for heavy in HEAVY:
        assert heavy not in mods, f"`import groundlens` pulled in {heavy}"


def test_verify_import_loads_no_heavy_libs() -> None:
    mods = _top_level_modules("import groundlens.verify")
    assert "groundlens" in mods
    for heavy in HEAVY:
        assert heavy not in mods, f"`import groundlens.verify` pulled in {heavy}"
