"""The version lives in three files. They must agree, and they have not.

``pyproject.toml`` is the source of truth: ``python -m build`` reads it, and the
wheel it produces is what PyPI stores. The other two are copies:

- ``_version.py`` carries a ``_FALLBACK`` for running from a source tree that
  was never installed. Its own docstring says "keep it in step with
  pyproject.toml when you cut a release", which is a comment, not a check.
- ``CITATION.cff`` is what GitHub renders as the citation block and what
  reference managers read. A stale version there is a wrong citation.

Nothing enforced any of this. At 2026.7.28 the CHANGELOG had no entry for the
released version at all and carried two separate ``Unreleased`` headings, which
is the same drift one step further along.

The release-tag failure mode is worth naming because it is silent until it is
not: the tag does not set the version. ``.github/workflows/release.yml`` fires
on ``v*`` and runs ``python -m build``, which reads ``pyproject.toml``. Tagging
``v2026.8.5`` on a tree that still says ``2026.7.28`` builds a 2026.7.28 wheel,
and PyPI rejects it as a file that already exists — after the tag is pushed and
the release is public.
"""

from __future__ import annotations

import datetime
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
VERSION_PY = REPO / "src" / "groundlens" / "_version.py"
CITATION = REPO / "CITATION.cff"
CHANGELOG = REPO / "CHANGELOG.md"

#: SemVer, MAJOR.MINOR.PATCH, from 2.0.0 onward. v2 has a public contract --
#: finding codes, the audit record schema, the pack format -- and a date cannot
#: tell a caller when that contract breaks.
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

#: CalVer, YYYY.M.D, with no zero padding on month or day. Used up to 2026.8.5.
CALVER = re.compile(r"^(20\d{2})\.(1[0-2]|[1-9])\.(3[01]|[12]\d|[1-9])$")


def _pyproject_version() -> str:
    match = re.search(r'^version = "([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M)
    assert match, "pyproject.toml has no [project] version"
    return match.group(1)


def _fallback_version() -> str:
    match = re.search(r'^_FALLBACK = "([^"]+)"', VERSION_PY.read_text(encoding="utf-8"), re.M)
    assert match, "_version.py has no _FALLBACK"
    return match.group(1)


def _citation_version() -> str:
    match = re.search(r"^version: (.+)$", CITATION.read_text(encoding="utf-8"), re.M)
    assert match, "CITATION.cff has no version"
    return match.group(1).strip().strip('"')


def test_pyproject_and_fallback_agree() -> None:
    """A mismatch makes ``groundlens.__version__`` a lie in any source checkout."""
    assert _fallback_version() == _pyproject_version(), (
        f"_version.py _FALLBACK is {_fallback_version()} but pyproject.toml says "
        f"{_pyproject_version()}. Bump both when you cut a release."
    )


def test_citation_matches_pyproject() -> None:
    """A stale CITATION.cff is a wrong citation on the repo's front page."""
    assert _citation_version() == _pyproject_version(), (
        f"CITATION.cff is {_citation_version()} but pyproject.toml says {_pyproject_version()}."
    )


def test_citation_date_is_a_real_date() -> None:
    """SemVer does not encode the date, so date-released has to stand on its own.

    Under CalVer this test could derive the expected date from the version
    string. It cannot any more, so it checks the weaker thing that still
    matters: reference managers get a parseable ISO date, not a placeholder.
    """
    match = re.search(r'^date-released: "?([\d-]+)"?', CITATION.read_text(encoding="utf-8"), re.M)
    assert match, "CITATION.cff has no date-released"
    datetime.date.fromisoformat(match.group(1))


def test_version_is_semver() -> None:
    """MAJOR.MINOR.PATCH from 2.0.0 on. `groundlens>=2,<3` has to mean something."""
    version = _pyproject_version()
    assert SEMVER.match(version), f"{version} is not SemVer MAJOR.MINOR.PATCH"


def test_version_did_not_regress_to_calver() -> None:
    """A CalVer string sorts above 2.0.0 and would shadow every future release.

    `2026.8.5` > `2.0.0` under PEP 440, so one CalVer version published after
    the switch permanently outranks the SemVer line on PyPI and pip would never
    resolve a 2.x release again.
    """
    version = _pyproject_version()
    assert not CALVER.match(version), (
        f"{version} is CalVer. groundlens moved to SemVer at 2.0.0 and cannot move back: "
        "a CalVer release would sort above every 2.x and 3.x version forever."
    )


def test_installed_version_matches_source() -> None:
    """Catches a stale editable install pointing at another checkout."""
    import groundlens

    if groundlens.__file__ is None:
        pytest.skip("namespace package")
    installed_from = pathlib.Path(groundlens.__file__).resolve()
    if REPO not in installed_from.parents:
        pytest.skip(f"groundlens is installed from {installed_from}, not this tree")
    assert groundlens.__version__ == _pyproject_version(), (
        f"groundlens.__version__ is {groundlens.__version__} but this tree says "
        f"{_pyproject_version()}. Re-run `pip install -e .`."
    )


def test_changelog_has_an_entry_for_this_version() -> None:
    """2026.7.28 shipped with no CHANGELOG entry. Once is enough."""
    version = _pyproject_version()
    headings = re.findall(r"^## (.+)$", CHANGELOG.read_text(encoding="utf-8"), re.M)
    assert any(h.startswith(version) for h in headings), (
        f"CHANGELOG.md has no `## {version}` section. Releasing without one is how "
        f"2026.7.28 ended up undocumented."
    )


def test_changelog_has_at_most_one_unreleased_section() -> None:
    """Two `Unreleased` headings means half the notes get missed at release."""
    headings = re.findall(r"^## (.+)$", CHANGELOG.read_text(encoding="utf-8"), re.M)
    unreleased = [h for h in headings if h.strip().strip("[]").lower() == "unreleased"]
    assert len(unreleased) <= 1, (
        f"CHANGELOG.md has {len(unreleased)} Unreleased sections: {unreleased}. "
        "Merge them, or the older one ships undocumented."
    )
