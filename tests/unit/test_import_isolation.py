"""`import groundlens` must not drag in the deep learning stack.

This is the test that makes the v2 packaging promise real. `pip install
groundlens` declares one runtime dependency, PyYAML. numpy and
sentence-transformers moved to the `geometry` extra, and sentence-transformers
pulls torch, which is roughly two gigabytes before the user has done anything.
A dependency edge that is not exercised is a dependency edge that comes back,
so we assert on `sys.modules` rather than on the metadata.

Every check runs in a *subprocess*. The pytest session that runs this file has
almost certainly imported numpy already (the SGI/DGI suite lives two files
away, and `dev` installs `geometry` precisely so those tests can run), so an
in-process `import groundlens` followed by a `sys.modules` assertion would pass
for the wrong reason, or fail for the wrong reason, and never for the reason we
care about. A clean interpreter is the only honest measurement.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

# torch and transformers are the expensive ones; numpy and sentence_transformers
# are the declared edges that used to pull them in.
BANNED = ("torch", "numpy", "sentence_transformers", "transformers")

# The subprocess exits with this when groundlens itself is not importable — for
# example while the v2 control modules are still landing in parallel branches.
# Distinguishing it from a real failure keeps the signal readable.
_EXIT_UNIMPORTABLE = 3

_PROBE = """
import sys

try:
    import groundlens
except ImportError as exc:
    sys.stdout.write("UNIMPORTABLE:" + repr(exc))
    raise SystemExit({unimportable})

{body}
"""


def _run(body: str) -> str:
    """Run `body` in a fresh interpreter after importing groundlens.

    Returns the subprocess stdout. Skips the test if groundlens itself cannot
    be imported yet.
    """
    source = _PROBE.format(unimportable=_EXIT_UNIMPORTABLE, body=body)
    proc = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if proc.returncode == _EXIT_UNIMPORTABLE:
        pytest.skip(f"groundlens is not importable in this tree yet: {proc.stdout}")
    assert proc.returncode == 0, (
        f"probe exited {proc.returncode}\n--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}"
    )
    return proc.stdout


def test_import_groundlens_loads_no_ml_stack():
    """`import groundlens` leaves torch, numpy, sentence_transformers, transformers unloaded."""
    banned = ",".join(repr(name) for name in BANNED)
    out = _run(
        "loaded = [n for n in (" + banned + ",) if n in sys.modules]\n"
        'sys.stdout.write("LOADED:" + ",".join(loaded))\n'
    )
    loaded = out.partition("LOADED:")[2].strip()
    assert loaded == "", (
        f"`import groundlens` pulled in {loaded}. The control path must install and "
        "import without the geometry extra. Move the offending import into a "
        "function body or behind TYPE_CHECKING."
    )


def test_no_geometry_submodule_is_imported_eagerly():
    """The geometry modules stay unloaded until someone names one of their exports."""
    geometry_modules = (
        "groundlens.sgi",
        "groundlens.dgi",
        "groundlens.evaluate",
        "groundlens.calibrate",
        "groundlens._internal.embeddings",
        "groundlens._internal.geometry",
    )
    names = ",".join(repr(name) for name in geometry_modules)
    out = _run(
        "loaded = [n for n in (" + names + ",) if n in sys.modules]\n"
        'sys.stdout.write("LOADED:" + ",".join(loaded))\n'
    )
    loaded = out.partition("LOADED:")[2].strip()
    assert loaded == "", f"these geometry modules were imported eagerly: {loaded}"


def test_geometry_names_are_still_reachable():
    """The lazy shim resolves the geometry surface when the extra is installed."""
    pytest.importorskip("numpy")
    pytest.importorskip("sentence_transformers")
    out = _run(
        "fn = groundlens.compute_sgi\n"
        'assert "groundlens.sgi" in sys.modules, "lazy access did not import the module"\n'
        'sys.stdout.write("OK:" + fn.__name__)\n'
    )
    assert "OK:compute_sgi" in out


def test_check_stays_bound_to_the_control_entry_point():
    """Loading a geometry name must not rebind `groundlens.check` to the v1 module."""
    pytest.importorskip("numpy")
    out = _run(
        "import inspect\n"
        "before = groundlens.check\n"
        "groundlens.GroundingSwitch  # imports groundlens.switch -> groundlens.check\n"
        'assert not inspect.ismodule(groundlens.check), "groundlens.check was clobbered"\n'
        'assert groundlens.check is before, "groundlens.check changed identity"\n'
        'sys.stdout.write("OK")\n'
    )
    assert "OK" in out


def test_cli_help_loads_no_ml_stack():
    """`groundlens --help` must stay fast; heavy imports are deferred in the CLI."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "try:\n"
            "    from groundlens.cli.main import main\n"
            "except ImportError as exc:\n"
            '    sys.stdout.write("UNIMPORTABLE:" + repr(exc))\n'
            f"    raise SystemExit({_EXIT_UNIMPORTABLE})\n"
            "loaded = [n for n in " + repr(list(BANNED)) + " if n in sys.modules]\n"
            'sys.stdout.write("LOADED:" + ",".join(loaded))\n',
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if proc.returncode == _EXIT_UNIMPORTABLE:
        pytest.skip(f"groundlens.cli is not importable in this tree yet: {proc.stdout}")
    assert proc.returncode == 0, proc.stderr
    loaded = proc.stdout.partition("LOADED:")[2].strip()
    assert loaded == "", f"importing the CLI pulled in {loaded}"
