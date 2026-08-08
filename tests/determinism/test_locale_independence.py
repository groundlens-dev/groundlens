"""Rules 3, 4 and 7: the host has no vote.

Two halves. The first runs the parser under mutated ``LC_ALL`` and
``LANG`` and under a really changed C locale, and asserts the output is
identical. The second is a source scan: an AST pass over the
deterministic modules that fails on any call to ``locale.setlocale``,
``date.today``, ``datetime.now``, anything on ``random``, or ``float()``.

The scan is AST-based and not a text search on purpose. The modules
under test *describe* these forbidden calls in their docstrings, because
they are the rules contributors need to read; a grep would fire on the
documentation and the obvious fix would be to stop documenting the rule.
An AST pass sees calls and ignores prose.

Adding a module to :data:`DETERMINISTIC_MODULES` puts it under the same
gate. That list is meant to grow as the control path lands: the matcher,
the rule engine and the pack loader all belong in it.
"""

from __future__ import annotations

import ast
import locale
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from groundlens.determinism import (
    LOCALE_PROFILES,
    canonical_decimal_str,
    get_locale_profile,
    normalise_text,
    parse_decimal,
)

from ._helpers import record_digest_in_subprocess
from ._sample import build_sample_record

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
_SRC = _REPO / "src" / "groundlens"

DETERMINISTIC_MODULES: tuple[str, ...] = (
    "types.py",
    "audit_record.py",
    "determinism.py",
)
"""Modules held to the determinism rules by the source scan.

Extend this as the v2 control path lands. Anything on the decision path
belongs here: ``control.py``, ``extract/``, ``match.py``, ``packs.py``.
"""

FORBIDDEN_CALLS: tuple[str, ...] = (
    "locale.setlocale",
    "date.today",
    "datetime.now",
    "datetime.utcnow",
    "datetime.today",
    "time.time",
    "float",
)
"""Dotted call names no deterministic module may contain."""

FORBIDDEN_MODULES: tuple[str, ...] = ("random", "locale", "secrets")
"""Modules no deterministic module may import or touch."""


# ── Half one: behaviour does not move with the environment ──────────────────


_ENV_VARIANTS: tuple[dict[str, str], ...] = (
    {"LC_ALL": "C", "LANG": "C"},
    {"LC_ALL": "de_DE.UTF-8", "LANG": "de_DE.UTF-8"},
    {"LC_ALL": "tr_TR.UTF-8", "LANG": "tr_TR.UTF-8"},
    {"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8", "LC_NUMERIC": "fr_FR.UTF-8"},
)

_PARSE_CASES: tuple[tuple[str, str, str], ...] = (
    ("eu-es", "1.234,56", "1234.56"),
    ("eu-de", "1.234,56", "1234.56"),
    ("en-us", "1,234.56", "1234.56"),
    ("en-gb", "1,234.56", "1234.56"),
    ("iso", "1234.56", "1234.56"),
    ("eu-es", "0,50", "0.5"),
    ("eu-es", "(1.234,56)", "-1234.56"),
)


@pytest.mark.parametrize("env", _ENV_VARIANTS)
def test_parse_decimal_ignores_environment_locale(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for profile_name, raw, expected in _PARSE_CASES:
        parsed = parse_decimal(raw, get_locale_profile(profile_name))
        assert canonical_decimal_str(parsed) == expected


@pytest.mark.parametrize("env", _ENV_VARIANTS)
def test_record_digest_ignores_environment_locale(env: dict[str, str]) -> None:
    from groundlens.audit_record import record_sha256

    baseline = record_sha256(build_sample_record())
    assert record_digest_in_subprocess(env) == baseline


def test_parse_decimal_survives_a_really_changed_c_locale() -> None:
    """Env vars alone do nothing until something calls ``setlocale``.

    So the test calls it, which library code may not. If the locale is
    not installed on the runner the test skips rather than passing
    vacuously.
    """
    profile = get_locale_profile("eu-es")
    before = parse_decimal("1.234,56", profile)
    original = locale.setlocale(locale.LC_ALL)
    try:
        try:
            locale.setlocale(locale.LC_ALL, "de_DE.UTF-8")
        except locale.Error:
            pytest.skip("de_DE.UTF-8 not available on this host")
        after = parse_decimal("1.234,56", profile)
    finally:
        locale.setlocale(locale.LC_ALL, original)
    assert before == after == Decimal("1234.56")


def test_normalise_text_is_idempotent() -> None:
    samples = (
        "  \ufb01rst\r\n\n  1\u00a0234  ",
        "soft\u00adhyphen zero\u200bwidth",
        "1\u20444 and \uff11\uff12\uff13",
        "",
        "   ",
    )
    for sample in samples:
        once = normalise_text(sample)
        assert normalise_text(once) == once


def test_every_shipped_locale_profile_is_well_formed() -> None:
    required = {"eu-es", "eu-de", "en-gb", "en-us", "iso"}
    assert required <= set(LOCALE_PROFILES)
    for name, profile in LOCALE_PROFILES.items():
        assert profile.name == name
        assert profile.date_order in {"dmy", "mdy", "ymd"}
        assert profile.decimal_separator != profile.thousands_separator


def test_locale_confusion_is_loud_not_silent() -> None:
    """``1.23`` is not a thousands group, so eu-es must refuse it."""
    with pytest.raises(ValueError, match="grouping"):
        parse_decimal("1.23", get_locale_profile("eu-es"))


# ── Half two: the source scan ───────────────────────────────────────────────


def _dotted(node: ast.expr) -> str:
    """Render an attribute/name expression as a dotted string, best effort."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _scan(path: Path) -> list[str]:
    """Return every determinism violation found in one source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name in FORBIDDEN_CALLS or name.split(".")[0] in FORBIDDEN_MODULES:
                violations.append(f"{path.name}:{node.lineno} calls {name}()")
        elif isinstance(node, ast.Attribute):
            root = _dotted(node).split(".")[0]
            if root in FORBIDDEN_MODULES:
                violations.append(f"{path.name}:{node.lineno} touches {_dotted(node)}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                    violations.append(f"{path.name}:{node.lineno} imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_MODULES:
                violations.append(f"{path.name}:{node.lineno} imports from {node.module}")

    return violations


@pytest.mark.parametrize("module_name", DETERMINISTIC_MODULES)
def test_module_has_no_forbidden_calls(module_name: str) -> None:
    path = _SRC / module_name
    assert path.is_file(), f"{module_name} is listed in DETERMINISTIC_MODULES but does not exist"
    assert _scan(path) == []


def test_scanner_actually_detects_violations(tmp_path: Path) -> None:
    """A scanner that never fires is decoration."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import random\n"
        "import locale\n"
        "from datetime import date\n"
        "def f(x):\n"
        "    locale.setlocale(locale.LC_ALL, '')\n"
        "    return float(x) + random.random() + date.today().toordinal()\n",
        encoding="utf-8",
    )
    violations = _scan(planted)
    joined = " ".join(violations)
    assert "imports random" in joined
    assert "imports locale" in joined
    assert "calls locale.setlocale()" in joined
    assert "calls float()" in joined
    assert "calls random.random()" in joined
    assert "calls date.today()" in joined


def test_scanner_ignores_prose() -> None:
    """The rules are documented in these modules; documentation is not a call."""
    source = (_SRC / "determinism.py").read_text(encoding="utf-8")
    assert "locale.setlocale" in source, "the module should still document rule 3"
    assert "datetime.now" in source, "the module should still document rule 4"
    assert _scan(_SRC / "determinism.py") == []


@pytest.mark.parametrize("module_name", DETERMINISTIC_MODULES)
def test_module_imports_only_the_standard_library(module_name: str) -> None:
    """No third-party import may appear in a deterministic module."""
    stdlib = set(sys.stdlib_module_names)
    tree = ast.parse((_SRC / module_name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in stdlib or root == "groundlens", alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            root = (node.module or "").split(".")[0]
            assert root in stdlib or root == "groundlens", node.module
