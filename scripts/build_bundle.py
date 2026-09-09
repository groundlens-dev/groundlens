#!/usr/bin/env python3
"""Build the `base` bundle: multilingual-e5-small (f32) for the lexical channel.

The model and tokenizer are the ONNX export published by the model authors
on the Hugging Face Hub, taken at a pinned revision so the bundle can be
rebuilt byte for byte. The archive is written with fixed metadata, so the
same inputs give the same sha256 everywhere.

    python scripts/build_bundle.py --out dist/bundle
    → dist/bundle/groundlens-base-v1.tar.gz
      dist/bundle/groundlens-base-v1.tar.gz.sha256
      dist/bundle/manifest.json

This script runs in CI (.github/workflows/bundle.yml) and publishes to a
GitHub Release. The engine pins the archive sha256 in
crates/gl-bundle/src/lib.rs (KNOWN_BUNDLES) so `groundlens bundle pull base`
refuses anything else.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path

NAME = "base"
VERSION = "1"
MODEL_REPO = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILES = {
    "models/multilingual-e5-small.onnx": "onnx/model.onnx",
    "tokenizers/multilingual-e5-small/tokenizer.json": "onnx/tokenizer.json",
}
ENCODER = {
    "model": "models/multilingual-e5-small.onnx",
    "tokenizer": "tokenizers/multilingual-e5-small/tokenizer.json",
    # 512 positions, minus [CLS]/[SEP], minus the "query: " prefix tokens,
    # with margin.
    "max_tokens": 500,
    "prefix": "query: ",
    "pooling": "mean",
    "dim": 384,
}
ENGINE_VERSION = "4.0.0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def download(rel: str, dest: Path) -> None:
    url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{rel}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"fetch {url}")
    with urllib.request.urlopen(url) as resp, dest.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(resp, out)


def deterministic_targz(root: Path, arcroot: str, out: Path) -> None:
    """tar with fixed mtime/owner/mode, sorted names; gzip without timestamp."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(p for p in root.rglob("*")):
            info = tar.gettarinfo(str(path), arcname=f"{arcroot}/{path.relative_to(root).as_posix()}")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            info.mode = 0o755 if path.is_dir() else 0o644
            if path.is_file():
                with path.open("rb") as f:
                    tar.addfile(info, f)
            else:
                tar.addfile(info)
    with out.open("wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
        gz.write(buf.getvalue())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/bundle")
    args = ap.parse_args()
    out = Path(args.out)
    stage = out / f"groundlens-{NAME}-v{VERSION}"
    if stage.exists():
        shutil.rmtree(stage)
    for rel, src in FILES.items():
        download(src, stage / rel)

    artefacts = {}
    for rel in FILES:
        p = stage / rel
        artefacts[rel] = {
            "path": rel,
            "sha256": sha256_file(p),
            "bytes": p.stat().st_size,
            "kind": "onnx-model" if rel.endswith(".onnx") else "tokenizer",
            "used_by": ["groundlens.lexical"],
        }
    manifest = {
        "schema": "groundlens.bundle-manifest/1",
        "name": NAME,
        "version": VERSION,
        "engine_version": ENGINE_VERSION,
        "execution_profile": "cpu-f32",
        "artefacts": artefacts,
        "offline_only": True,
        "encoders": {"default": ENCODER},
        "provenance": {"model": MODEL_REPO, "revision": MODEL_REVISION, "files": FILES},
    }
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (stage / "manifest.json").write_text(text)
    (out / "manifest.json").write_text(text)

    archive = out / f"groundlens-{NAME}-v{VERSION}.tar.gz"
    deterministic_targz(stage, stage.name, archive)
    digest = sha256_file(archive)
    (out / (archive.name + ".sha256")).write_text(f"{digest.split(':')[1]}  {archive.name}\n")
    print(f"{archive}  {archive.stat().st_size} bytes  {digest}")
    print("pin this in crates/gl-bundle/src/lib.rs KNOWN_BUNDLES.archive_sha256")


if __name__ == "__main__":
    main()
