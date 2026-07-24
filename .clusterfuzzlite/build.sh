#!/bin/bash -eu
# Install the package, then compile every fuzz target under fuzz/.
pip3 install .
for fuzzer in "$SRC/groundlens"/fuzz/fuzz_*.py; do
  compile_python_fuzzer "$fuzzer"
done
