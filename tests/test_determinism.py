from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from groundlens._numerals import find_numerals, locale
from groundlens._words import segment
from scripts.dump_fixture import dump

GOLDEN = Path(__file__).parent / "golden_structural.json"


def test_structural_output_matches_the_committed_golden_file() -> None:
    """If this fails, either you changed behaviour or you changed it by accident.

    Regenerate with ``python scripts/dump_fixture.py > tests/golden_structural.json``
    and read the diff before you commit it. That diff is the whole point.
    """
    assert dump() == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_output_is_stable_across_processes() -> None:
    """Fresh interpreter, randomised hash seed, hostile locale. Byte for byte."""
    env = {
        **os.environ,
        "PYTHONHASHSEED": "random",
        "LC_ALL": "tr_TR.UTF-8",
        "LANG": "tr_TR.UTF-8",
    }
    root = Path(__file__).parent.parent
    runs = {
        subprocess.run(
            [sys.executable, "scripts/dump_fixture.py"],
            cwd=root,
            env=env,
            capture_output=True,
            check=True,
        ).stdout
        for _ in range(3)
    }
    assert len(runs) == 1, "same input produced different bytes across processes"


def test_the_environment_cannot_change_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LC_ALL", "LANG", "LC_NUMERIC", "TZ"):
        monkeypatch.setenv(name, "de_DE.UTF-8")
    assert find_numerals("1,234", locale("en"))[0].readings == (Decimal("1234"),)
    assert find_numerals("1,234", locale("es"))[0].readings == (Decimal("1.234"),)


def test_no_float_anywhere_in_the_numeral_path() -> None:
    """Numerals are Decimal end to end. A float here is a reproducibility bug."""
    for numeral in find_numerals("1.000,50 and 10,000 and 3.5%", locale("es")):
        for reading in numeral.readings:
            assert isinstance(reading, Decimal)


def test_unit_ordering_does_not_depend_on_dict_or_set_iteration() -> None:
    text = "10,000 dollars and 30 days and 1.250,50 EUR"
    once = [(u.text, u.span, u.kind) for u in segment(text, locale("und"))]
    twice = [(u.text, u.span, u.kind) for u in segment(text, locale("und"))]
    assert once == twice
    assert once == sorted(once, key=lambda row: row[1])
