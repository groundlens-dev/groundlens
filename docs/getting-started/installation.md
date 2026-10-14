# Installation

## The package

```{code-block} bash
pip install groundlens
```

The wheel carries the engine as a compiled Rust extension. It has **no runtime
dependencies**, needs **no model** and opens **no network connection**.

Python 3.10 or newer, on Linux, macOS or Windows. Wheels are `abi3`, one per
platform, so a single wheel covers every supported Python on that platform.

Installing gives you the `groundlens` Python package and the `groundlens`
command.

```{code-block} bash
python -c "import groundlens; print(groundlens.__version__)"
groundlens --version
```

## Checking records without Python

Whoever has to check the records, an auditor or another team, does not need
Python. Each [release](https://github.com/groundlens-dev/groundlens/releases)
has a single `glv` binary for Linux, macOS and Windows that verifies records
and shows the policy a record names, with its hash:

```{code-block} bash
glv record verify records.jsonl
glv policy show eu_ai_act_high_risk_v1 --resolved
```

## From source

The engine is a Rust workspace with Python bindings built by
[maturin](https://www.maturin.rs/). To build the wheel yourself:

```{code-block} bash
git clone https://github.com/groundlens-dev/groundlens
cd groundlens/python
pip install maturin
maturin develop --release
```

This compiles the Rust extension and installs `groundlens` into the active
environment.
