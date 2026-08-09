#!/bin/bash -eu
# Build the fuzz targets.
#
# Three things here are deliberate.
#
# --no-deps, then explicit pins: the targets exercise the deterministic output
# layer, which is pure Python. Installing the dependency tree wholesale would
# pull sentence-transformers and torch, gigabytes for nothing, so every module
# the import graph genuinely needs is installed by hand below.
#
# pyyaml: groundlens/__init__.py imports the control path eagerly, which
# reaches packs/loader.py, which imports yaml at module level. Without this the
# frozen target raises ModuleNotFoundError at startup and every fuzz run is
# reported as a bad build. Atheris instruments the whole package before it
# reaches the symbol the target actually calls, so "the target does not parse
# YAML" is not a reason to leave it out.
#
# numpy is deliberately NOT installed any more. In 1.x it entered the bundle
# because __init__.py imported every submodule eagerly and sgi/dgi reached
# _internal/embeddings.py. In 2.x the geometry surface is lazy (PEP 562), so
# numpy is no longer in the import graph. The instrumentation log confirms it:
# groundlens, control, facts, packs and loader are instrumented; numpy is not.
# It is dropped rather than left in because the pin had already broken this
# build once (numpy 2.4.6 shipped internals the image's PyInstaller hook does
# not collect), and an unused dependency that has broken the build before is
# pure downside. If a future target reaches geometry, add it back with a pin
# and a green run, not by leaving it open.
#
# The pyyaml pin: the base image is pinned by digest, so resolving pyyaml fresh
# on every build would leave the build only half reproducible. Raise it
# deliberately, with a green run.
pip3 install --no-deps .
pip3 install "pyyaml==6.0.2"

for fuzzer in "$SRC/groundlens"/fuzz/fuzz_*.py; do
  # --collect-all yaml tells PyInstaller to bundle the package wholesale
  # rather than trusting a hook that may be older than the installed version.
  # Belt and braces alongside the pin: if the pin is ever raised and the hook
  # is stale, this is what stops the target silently building broken.
  compile_python_fuzzer "$fuzzer" --collect-all yaml
done
