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

## No model needed

Everything in the default path works out of the box, with no model and no
network: numbers, currencies, percentages and units, the scope check, symbolic
rules, and the signed record. The shipped policies use only these checks.

## The model bundle (deprecated)

```{admonition} Deprecated
:class: warning
The lexical, entailment and similarity channels are deprecated. On the answers
we measured they did not add value: they check that words are present, not
that a figure is bound to the right company, year or clause. They are off
unless you ask for them, and they leave the default build in the next release.
See the [design page](../design/next.md).
```

The model channels need a model, and models are distributed as a **bundle**: a
directory of ONNX graphs, tokenizers and checksums that the engine verifies by
hash before it uses anything. If you still need them, install the `base`
bundle once:

```{code-block} bash
groundlens bundle pull base
```

This downloads about 470 MB, checks the archive against a hash pinned inside
the engine, unpacks it into a per-user directory, and re-hashes every artefact.
If any hash does not match, nothing is installed. See [Bundles](bundles.md) for
where it lands, how to move it, and how to run fully offline.

An installed bundle is used only when a call names it: `--bundle base` on the
command line, `bundle="base"` in Python. Naming one prints a deprecation
warning.

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
