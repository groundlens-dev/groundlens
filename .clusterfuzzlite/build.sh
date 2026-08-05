#!/bin/bash -eu
# Build the fuzz targets.
#
# Two things here are deliberate.
#
# --no-deps, then an explicit numpy: the targets exercise the deterministic
# output layer, which is pure Python. numpy only enters the bundle because
# groundlens/__init__.py imports every submodule eagerly, and sgi/dgi reach
# _internal/embeddings.py which imports it at module level. sentence-
# transformers and torch are imported lazily inside functions, so they never
# enter the graph and installing them here would add gigabytes for nothing.
#
# The numpy pin: the base image is pinned by digest, but `pip install .`
# resolved numpy fresh on every build, so the build was only half
# reproducible. It broke when numpy 2.4.6 arrived with internals the
# PyInstaller hook in this image does not collect (No module named
# 'numpy._core._exceptions'). Pinning here makes the build deterministic.
# Raise it deliberately, with a green run, not by leaving it open.
pip3 install --no-deps .
pip3 install "numpy==2.2.6"

for fuzzer in "$SRC/groundlens"/fuzz/fuzz_*.py; do
  # --collect-all numpy tells PyInstaller to bundle the package wholesale
  # rather than trusting a hook that may be older than the installed version.
  # Belt and braces alongside the pin: if the pin is ever raised and the hook
  # is stale again, this is what stops the target silently building broken.
  compile_python_fuzzer "$fuzzer" --collect-all numpy
done
