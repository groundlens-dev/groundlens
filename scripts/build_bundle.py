#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Build the `base` bundle (v2): the multilingual-e5-small encoder for the
lexical and semantic channels, and a multilingual NLI model for the entailment
channel.

The encoder is the ONNX export the model authors publish on the Hugging Face
Hub, taken at a pinned revision and downloaded as-is. The NLI model ships only
as PyTorch, so it is exported to ONNX with `optimum` at a pinned opset; the
export is byte-reproducible on the pinned toolchain in scripts/requirements-
bundle.txt. The archive is written with fixed metadata, so the same inputs give
the same sha256 everywhere.

    python scripts/build_bundle.py --out dist/bundle
    → dist/bundle/groundlens-base-v2.tar.gz
      dist/bundle/groundlens-base-v2.tar.gz.sha256
      dist/bundle/manifest.json

This runs in CI (.github/workflows/bundle.yml) and publishes to a GitHub
Release. The engine pins the archive sha256 in crates/gl-bundle/src/lib.rs
(KNOWN_BUNDLES) so `groundlens bundle pull base` refuses anything else.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

NAME = "base"
VERSION = "2"

# --- Encoder: multilingual-e5-small, the authors' ONNX export (downloaded). ---
ENC_REPO = "intfloat/multilingual-e5-small"
ENC_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
ENC_FILES = {
    "models/multilingual-e5-small.onnx": "onnx/model.onnx",
    "tokenizers/multilingual-e5-small/tokenizer.json": "onnx/tokenizer.json",
}
# The encoder feeds both the lexical (word anchors) and semantic (sentence
# similarity) channels.
ENC_USED_BY = ["groundlens.lexical", "semantic.cosine"]
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

# --- NLI: a multilingual entailment model, exported to ONNX with optimum. ---
NLI_REPO = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"
# TODO: pin to the commit sha this build resolves and prints (recorded in
# provenance), so the ONNX export is reproducible to a fixed model revision.
NLI_REVISION = "main"
# tract 0.23 runs the tiny NLI test model at opset 13; export the real one the
# same way so the graph stays within what the engine's runtime supports.
NLI_OPSET = 13
NLI_MODEL_PATH = "models/nli-multilingual-minilmv2-l6.onnx"
NLI_TOKENIZER_PATH = "tokenizers/nli-multilingual-minilmv2-l6/tokenizer.json"
NLI_USED_BY = ["groundlens.nli"]
# Total tokens (specials included) per (premise, hypothesis) pair; the engine
# truncates longer pairs, keeping the trailing [SEP]. Under the 512-position
# limit of the XLM-R backbone.
NLI_MAX_TOKENS = 500

ENGINE_VERSION = "4.0.0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def download(repo: str, revision: str, rel: str, dest: Path) -> None:
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{rel}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"fetch {url}")
    with urllib.request.urlopen(url) as resp, dest.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(resp, out)


def export_nli(stage: Path) -> tuple[list[str], str]:
    """Export the NLI model to ONNX with optimum. Returns (labels, resolved
    commit sha). The labels come from the model's own config, in logit order,
    so the manifest never disagrees with the graph."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_out = Path(tmp) / "nli"
        cmd = [
            sys.executable, "-m", "optimum.commands.optimum_cli",
            "export", "onnx",
            "--model", NLI_REPO,
            "--revision", NLI_REVISION,
            "--task", "text-classification",
            "--opset", str(NLI_OPSET),
            "--framework", "pt",
            str(tmp_out),
        ]
        print("export", " ".join(cmd))
        subprocess.run(cmd, check=True)

        (stage / NLI_MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)
        (stage / NLI_TOKENIZER_PATH).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp_out / "model.onnx", stage / NLI_MODEL_PATH)
        shutil.copyfile(tmp_out / "tokenizer.json", stage / NLI_TOKENIZER_PATH)

        config = json.loads((tmp_out / "config.json").read_text())
        id2label = config["id2label"]
        labels = [id2label[str(i)].lower() for i in range(len(id2label))]

    # Record the exact revision the export resolved to, so it can be pinned.
    resolved = NLI_REVISION
    try:
        from huggingface_hub import HfApi  # type: ignore

        resolved = HfApi().model_info(NLI_REPO, revision=NLI_REVISION).sha or NLI_REVISION
    except Exception as e:  # noqa: BLE001 - provenance is best effort
        print(f"note: could not resolve NLI revision sha ({e})")
    return labels, resolved


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


def artefact(stage: Path, rel: str, used_by: list[str]) -> dict:
    p = stage / rel
    return {
        "path": rel,
        "sha256": sha256_file(p),
        "bytes": p.stat().st_size,
        "kind": "onnx-model" if rel.endswith(".onnx") else "tokenizer",
        "used_by": used_by,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/bundle")
    args = ap.parse_args()
    out = Path(args.out)
    stage = out / f"groundlens-{NAME}-v{VERSION}"
    if stage.exists():
        shutil.rmtree(stage)

    # Encoder: download the authors' ONNX.
    for rel, src in ENC_FILES.items():
        download(ENC_REPO, ENC_REVISION, src, stage / rel)
    # NLI: export to ONNX.
    nli_labels, nli_revision = export_nli(stage)

    artefacts = {}
    for rel in ENC_FILES:
        artefacts[rel] = artefact(stage, rel, ENC_USED_BY)
    for rel in (NLI_MODEL_PATH, NLI_TOKENIZER_PATH):
        artefacts[rel] = artefact(stage, rel, NLI_USED_BY)

    manifest = {
        "schema": "groundlens.bundle-manifest/1",
        "name": NAME,
        "version": VERSION,
        "engine_version": ENGINE_VERSION,
        "execution_profile": "cpu-f32",
        "artefacts": artefacts,
        "offline_only": True,
        "encoders": {"default": ENCODER},
        "entailment": {
            "default": {
                "model": NLI_MODEL_PATH,
                "tokenizer": NLI_TOKENIZER_PATH,
                "max_tokens": NLI_MAX_TOKENS,
                "labels": nli_labels,
            }
        },
        "provenance": {
            "encoder": {"model": ENC_REPO, "revision": ENC_REVISION, "files": ENC_FILES},
            "nli": {
                "model": NLI_REPO,
                "revision": nli_revision,
                "opset": NLI_OPSET,
                "task": "text-classification",
            },
        },
    }
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (stage / "manifest.json").write_text(text)
    (out / "manifest.json").write_text(text)

    archive = out / f"groundlens-{NAME}-v{VERSION}.tar.gz"
    deterministic_targz(stage, stage.name, archive)
    digest = sha256_file(archive)
    (out / (archive.name + ".sha256")).write_text(f"{digest.split(':')[1]}  {archive.name}\n")
    print(f"{archive}  {archive.stat().st_size} bytes  {digest}")
    print(f"NLI model exported from {NLI_REPO} @ {nli_revision}, labels {nli_labels}")
    print("pin this in crates/gl-bundle/src/lib.rs KNOWN_BUNDLES.archive_sha256")
    print(f"pin NLI_REVISION in scripts/build_bundle.py to {nli_revision}")


if __name__ == "__main__":
    main()
