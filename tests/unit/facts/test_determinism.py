"""Determinism guarantees (contract section 5).

These are the tests that decide whether an audit record means anything.  If any
of them can be made to fail, the library's central claim is false.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date
from decimal import Context, Decimal, localcontext
from pathlib import Path

import pytest

from .conftest import USING_STUBS, make_profile

REF = date(2026, 2, 10)

SOURCE_DIR = Path(__file__).resolve().parents[3] / "src" / "groundlens" / "facts"

SAMPLE = (
    "If the account is closed, the firm must notify the customer within 30 days "
    "and must not disclose the records to third parties. The arrangement fee is "
    "1,250.50 EUR, a rise of 2.5%, and the report is due no later than 3 March 2026 "
    "under Article 12(3) of Reg. (EU) 2016/679 [3]. The customer need not respond. "
    "La entidad deberá informar al cliente en un plazo de 10 días hábiles."
)


@pytest.fixture(scope="module")
def gb():
    return make_profile(
        "en-gb", decimal_separator=".", group_separator=",", date_order="DMY", currency="GBP"
    )


def test_records_whether_this_run_used_the_real_modules_or_the_stubs():
    """Fails loudly in CI once the parallel branch lands, so nobody forgets."""
    if USING_STUBS:
        pytest.skip(
            "groundlens.types / groundlens.determinism not present; "
            "ran against the local stubs (see tests/unit/facts/_stub_*.py)"
        )
    import groundlens.determinism
    import groundlens.types

    assert hasattr(groundlens.types, "Fact")
    assert hasattr(groundlens.determinism, "LocaleProfile")


def test_extraction_is_identical_across_one_hundred_runs(gb):
    from groundlens.facts import extract_facts

    first = extract_facts(SAMPLE, locale=gb, reference_date=REF)
    assert first
    for _ in range(100):
        assert extract_facts(SAMPLE, locale=gb, reference_date=REF) == first


def test_matching_is_identical_across_one_hundred_runs(gb):
    from groundlens.facts import MatchConfig, extract_facts, match_facts
    from groundlens.types import Evidence

    facts = extract_facts(SAMPLE, locale=gb, reference_date=REF)
    evidence = [
        Evidence(id="doc-2#p1", text="The arrangement fee is 1,300.00 EUR."),
        Evidence(id="doc-1#p1", text="The firm may notify the customer within 30 days."),
    ]
    config = MatchConfig(reference_date=REF)
    first = match_facts(facts, evidence, locale=gb, config=config)
    assert first
    for _ in range(100):
        assert match_facts(facts, evidence, locale=gb, config=config) == first


@pytest.mark.parametrize(
    "environment",
    [
        {"LC_ALL": "C", "LANG": "C"},
        {"LC_ALL": "de_DE.UTF-8", "LANG": "de_DE.UTF-8"},
        {"LC_ALL": "es_ES.UTF-8", "LANG": "es_ES.UTF-8", "LC_NUMERIC": "es_ES.UTF-8"},
        {"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8", "LC_TIME": "ja_JP.UTF-8"},
        {"TZ": "Pacific/Kiritimati", "LANG": "tr_TR.UTF-8"},
    ],
)
def test_output_is_unchanged_under_mutated_locale_environment(gb, monkeypatch, environment):
    from groundlens.facts import extract_facts

    baseline = extract_facts(SAMPLE, locale=gb, reference_date=REF)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    assert extract_facts(SAMPLE, locale=gb, reference_date=REF) == baseline


def test_output_survives_a_hostile_ambient_decimal_context(gb):
    from groundlens.facts import extract_facts

    baseline = extract_facts(SAMPLE, locale=gb, reference_date=REF)
    with localcontext(Context(prec=1)):
        assert extract_facts(SAMPLE, locale=gb, reference_date=REF) == baseline


def test_output_does_not_depend_on_the_hash_seed():
    """A separate interpreter, a different PYTHONHASHSEED, the same tuple."""
    script = (
        "import sys; sys.path[:0] = ['src', 'tests']\n"
        "import unit.facts.conftest as c\n"
        "from datetime import date\n"
        "from groundlens.facts import extract_facts\n"
        "p = c.make_profile('en-gb', decimal_separator='.', group_separator=',',"
        " date_order='DMY', currency='GBP')\n"
        f"facts = extract_facts({SAMPLE!r}, locale=p, reference_date=date(2026, 2, 10))\n"
        "print([(f.kind.value, f.span, f.normalised, f.attrs) for f in facts])\n"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        environment = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": ""}
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=SOURCE_DIR.parents[2],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.add(result.stdout)
    assert len(outputs) == 1


# ---------------------------------------------------------------------------
# Source-level guards
# ---------------------------------------------------------------------------

SOURCES = sorted(SOURCE_DIR.glob("*.py"))


def code_only(path: Path) -> str:
    """The module's code with comments and every string literal removed.

    Scanning raw source would flag the prose that documents these very rules.
    """
    import tokenize

    kept = []
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type in {tokenize.COMMENT, tokenize.STRING}:
                continue
            kept.append(token.string)
    return " ".join(kept)


def test_the_source_tree_is_where_we_think_it_is():
    assert {path.name for path in SOURCES} >= {
        "normalise.py",
        "extract.py",
        "match.py",
        "lexicon.py",
        "config.py",
    }


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_wall_clock_in_the_deterministic_path(path):
    source = code_only(path)
    for forbidden in ("date . today", "datetime . now", "time . time", "utcnow"):
        assert forbidden not in source, f"{path.name} reads the clock"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_environment_locale_in_the_deterministic_path(path):
    source = code_only(path)
    for forbidden in ("setlocale", "getpreferredencoding", "LC_ALL", "environ", "getenv"):
        assert forbidden not in source, f"{path.name} reads the environment"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_float_construction_in_the_deterministic_path(path):
    code = code_only(path)
    assert not re.search(r"\bfloat \(", code), f"{path.name} builds a float"
    assert "import random" not in code
    assert "round (" not in code


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_only_the_stdlib_regex_engine(path):
    source = code_only(path)
    for banned in ("regex", "spacy", "dateutil", "numpy", "torch", "sentence_transformers"):
        assert banned not in source.split(), f"{path.name} imports {banned}"


def test_the_package_imports_nothing_heavy():
    script = (
        "import sys; sys.path.insert(0, 'src'); sys.path.insert(0, 'tests')\n"
        "import unit.facts.conftest\n"
        "import groundlens.facts.normalise\n"
        "banned = {'torch', 'sentence_transformers', 'transformers', 'spacy', 'regex',"
        " 'dateutil'}\n"
        "print(sorted(banned & set(sys.modules)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=SOURCE_DIR.parents[2],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]"


def test_attrs_and_findings_sort_stably(gb):
    from groundlens.facts import extract_facts

    facts = extract_facts(SAMPLE, locale=gb, reference_date=REF)
    for fact in facts:
        keys = [key for key, _ in fact.attrs]
        assert keys == sorted(keys)
    spans = [fact.span for fact in facts]
    assert spans == sorted(spans)


def test_decimal_comparisons_never_go_through_float(gb):
    from groundlens.facts.config import as_decimal

    assert as_decimal("0.1") + as_decimal("0.2") == Decimal("0.3")
