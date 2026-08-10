#!/bin/bash -eu
pip3 install "$SRC/groundlens"
for harness in "$SRC"/groundlens/fuzz/fuzz_*.py; do
  compile_python_fuzzer "$harness"
done
