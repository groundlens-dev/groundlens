"""Fixtures for the facts test suite.

``groundlens.types`` and ``groundlens.determinism`` are owned by a parallel
branch (contract sections 2 and 5).  Until they land, the stubs next to this
file are installed under those names so this branch is testable rather than
untested.  The moment the real modules exist they are used and the stubs are
ignored; ``USING_STUBS`` records which mode a run was in and one test asserts
on it, so a green suite cannot quietly mean "tested against my own stub".
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

CORPUS_DIR = Path(__file__).parent / "corpus"


def _install_stub(module_name: str, stub_name: str) -> bool:
    """Install ``stub_name`` as ``module_name`` if the real module is missing."""
    try:
        importlib.import_module(module_name)
    except ImportError:
        stub = importlib.import_module(f"{__package__}.{stub_name}")
        sys.modules[module_name] = stub
        package = importlib.import_module("groundlens")
        setattr(package, module_name.rsplit(".", 1)[1], stub)
        return True
    return False


_STUBBED_TYPES = _install_stub("groundlens.types", "_stub_types")
_STUBBED_DETERMINISM = _install_stub("groundlens.determinism", "_stub_determinism")
USING_STUBS = _STUBBED_TYPES or _STUBBED_DETERMINISM


def make_profile(
    name: str,
    *,
    decimal_separator: str,
    group_separator: str,
    date_order: str,
    currency: str | None = None,
):
    """Build a LocaleProfile without assuming the real constructor's shape.

    The real ``LocaleProfile`` is written on another branch.  Rather than guess
    its constructor, try the registry first, then keyword construction under
    each field-name spelling ``groundlens.facts.normalise`` knows about.
    """
    determinism = importlib.import_module("groundlens.determinism")
    profile_cls = determinism.LocaleProfile

    for getter in ("get_locale_profile", "get_profile", "profile_for", "for_name"):
        function = getattr(determinism, getter, None) or getattr(profile_cls, getter, None)
        if function is None:
            continue
        try:
            built = function(name)
        except Exception:
            continue
        if built is not None:
            return built

    attempts = (
        {
            "name": name,
            "decimal_separator": decimal_separator,
            "group_separator": group_separator,
            "date_order": date_order,
            "currency": currency,
        },
        {
            "name": name,
            "decimal_separator": decimal_separator,
            "thousands_separator": group_separator,
            "date_order": date_order,
        },
        {
            "name": name,
            "decimal_separator": decimal_separator,
            "group_separator": group_separator,
            "date_order": date_order,
        },
    )
    last: Exception | None = None
    for kwargs in attempts:
        try:
            return profile_cls(**kwargs)
        except TypeError as exc:  # pragma: no cover - depends on the real class
            last = exc
    pytest.skip(f"cannot construct LocaleProfile: {last}")


@pytest.fixture(scope="session")
def eu_es():
    return make_profile(
        "eu-es", decimal_separator=",", group_separator=".", date_order="DMY", currency="EUR"
    )


@pytest.fixture(scope="session")
def en_us():
    return make_profile(
        "en-us", decimal_separator=".", group_separator=",", date_order="MDY", currency="USD"
    )


@pytest.fixture(scope="session")
def en_gb():
    return make_profile(
        "en-gb", decimal_separator=".", group_separator=",", date_order="DMY", currency="GBP"
    )


@pytest.fixture(scope="session")
def profiles(eu_es, en_us, en_gb):
    return {"eu-es": eu_es, "en-us": en_us, "en-gb": en_gb}
