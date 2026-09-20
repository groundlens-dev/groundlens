# Bundles

A **bundle** is how GroundLens distributes models: a directory with a
`manifest.json` and, under it, the ONNX graphs, tokenizers, rule sets and
policies a deployment needs. Every artefact is listed in the manifest with its
sha256. The engine re-hashes each one when it opens the bundle and refuses to
start if any hash does not match. There is no partial trust.

## The base bundle

`base` carries the multilingual encoder (multilingual-e5-small, f32, 100
languages) that powers the lexical verifier.

```{code-block} bash
groundlens bundle pull base
groundlens bundle status base
```

`pull` downloads the archive, checks it against a hash pinned inside the engine,
unpacks it and re-hashes every artefact. Because the hash is pinned in the
build, a download is trusted only if it is exactly what this version of
GroundLens was released with.

## Where bundles live

By default, in the per-user data directory of the operating system:

- macOS: `~/Library/Application Support/groundlens/bundles/`
- Linux: `$XDG_DATA_HOME/groundlens/bundles/` or `~/.local/share/...`
- Windows: `%LOCALAPPDATA%\groundlens\bundles\`

Set `GROUNDLENS_BUNDLE_DIR` to override it. If that variable points straight at
a directory containing a `manifest.json`, that directory is used as the bundle,
whatever its name — handy for containers and air-gapped machines.

```{code-block} bash
export GROUNDLENS_BUNDLE_DIR=/opt/groundlens/base
groundlens verify --answer a.txt --source s=s.txt
```

## Running offline

Nothing about verification needs the network; only `pull` does. For an
air-gapped site, pull the bundle once on a connected machine, copy the
directory across, and point `GROUNDLENS_BUNDLE_DIR` at it. A bundle can also be
marked `offline_only`, in which case the engine refuses any verifier that would
need the network.

## The manifest, hashed into every record

When a verification uses a bundle, the bundle's manifest hash goes into the
record as `bundle_hash`. That ties every decision to the exact set of model
files that produced it: a record does not just say "the lexical verifier ran",
it says which encoder graph, by hash, did the work.

## Building your own bundle

Put your artefacts under the known sub-folders (`models`, `tokenizers`,
`calibration`, `rules`, `policies`) and write the manifest:

```{code-block} bash
groundlens bundle build path/to/bundle --name mybundle --bundle-version 1
groundlens bundle verify path/to/bundle
```

See {class}`groundlens.Bundle` for the Python interface.
