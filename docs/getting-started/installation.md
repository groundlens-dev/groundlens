# Installation

## The package

```{code-block} bash
pip install groundlens
```

The wheel carries the engine as a compiled Rust extension. It has **no runtime
dependencies** and opens **no network connection**. The only command that ever
touches the network is `groundlens bundle pull`, described below, and you run
that on purpose.

Python 3.10 or newer, on Linux, macOS or Windows. Wheels are `abi3`, one per
platform, so a single wheel covers every supported Python on that platform.

Installing gives you the `groundlens` Python package and two command-line
entry points, `groundlens` and `glv`.

```{code-block} bash
python -c "import groundlens; print(groundlens.__version__)"
groundlens --version
```

## The model bundle

The numeric and rules verifiers work out of the box. The **lexical** verifier
(and, in a later bundle, the entailment verifier) needs a model, and models are
distributed as a **bundle**: a directory of ONNX graphs, tokenizers and
checksums that the engine verifies by hash before it uses anything.

Install the `base` bundle once:

```{code-block} bash
groundlens bundle pull base
```

This downloads about 470 MB, checks the archive against a hash pinned inside
the engine, unpacks it into a per-user directory, and re-hashes every artefact.
If any hash does not match, nothing is installed. See [Bundles](bundles.md) for
where it lands, how to move it, and how to run fully offline.

```{admonition} You can skip the bundle
Verifying numbers, currencies, percentages, units and symbolic rules needs no
bundle at all. Add the bundle when you want the lexical channel or a policy
that requires it.
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
