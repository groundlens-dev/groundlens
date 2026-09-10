# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""A bundle is everything a verification needs, in one directory, with
checksums: models, tokenizers, calibrations, rules, policies.

``verify()`` never fetches anything. Fetching is a separate, explicit action
(``Bundle.pull`` or ``groundlens bundle pull``) so the engine can run in an
isolated environment, and a download is trusted only when its hash matches
the one pinned in this build of the engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from groundlens import _engine


class BundleError(RuntimeError):
    """A manifest is missing, an artefact hash does not match, or a download
    does not match the pinned hash."""


@dataclass(frozen=True)
class Bundle:
    root: Path
    name: str
    version: str
    hash: str

    @classmethod
    def open(cls, root: str | Path) -> Bundle:
        """Open a bundle and re-hash every artefact. Refuses on any mismatch."""
        try:
            name, version, manifest_hash = _engine.bundle_verify(str(root))
        except RuntimeError as e:
            raise BundleError(str(e)) from None
        return cls(root=Path(root), name=name, version=version, hash=manifest_hash)

    @classmethod
    def build(cls, root: str | Path, *, name: str, version: str) -> Bundle:
        """Write ``manifest.json`` for a directory laid out as models/,
        tokenizers/, calibration/, rules/, policies/."""
        _engine.bundle_build(str(root), name, version)
        return cls.open(root)

    @staticmethod
    def known() -> list[dict[str, str]]:
        """Bundles this build can fetch, with their pinned archive hashes."""
        return json.loads(_engine.known_bundles())

    @staticmethod
    def status(name: str = "base") -> dict[str, object]:
        """Whether ``name`` is installed, where, and with which hash."""
        return json.loads(_engine.bundle_status(name))

    @classmethod
    def installed(cls, name: str = "base") -> Bundle | None:
        """The installed bundle, opened and verified, or ``None``."""
        path = Path(_engine.bundle_locate(name))
        if not (path / "manifest.json").is_file():
            return None
        return cls.open(path)

    @classmethod
    def pull(
        cls,
        name: str = "base",
        *,
        into: str | Path | None = None,
        url: str | None = None,
        sha256: str | None = None,
        trust_unpinned: bool = False,
    ) -> Bundle:
        """Download a published bundle and install it.

        This is the one operation in the package that opens a network
        connection, and it only happens when you call it. The archive is
        hashed and compared with the value pinned in this build before a
        single file is unpacked. For a bundle this build does not know
        (your own, from your own ``url``), pass its ``sha256`` explicitly;
        ``trust_unpinned`` skips the check entirely and is for development.
        """
        import urllib.request  # imported here: nothing else in the package touches the network

        known = {b["name"]: b for b in cls.known()}
        if name not in known and url is None:
            raise BundleError(f"unknown bundle {name!r}; known: {', '.join(known) or 'none'}")
        entry = known.get(name, {})
        url = url or entry["url"]
        pinned = entry.get("archive_sha256", "sha256:unpinned")
        if sha256:
            pinned = sha256 if sha256.startswith("sha256:") else f"sha256:{sha256}"
        target = Path(into) if into else Path(_engine.bundle_locate(name))

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bundle.tar.gz"
            with urllib.request.urlopen(url) as resp, archive.open("wb") as out:  # noqa: S310
                shutil.copyfileobj(resp, out)
            digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
            if pinned == "sha256:unpinned":
                if not trust_unpinned:
                    raise BundleError(
                        f"this build has no pinned hash for bundle {name!r} (downloaded {digest}); "
                        "refusing to install it. Pass trust_unpinned=True only in development."
                    )
            elif digest != pinned:
                raise BundleError(f"download hash {digest} does not match the pinned {pinned}; not installed")
            staging = Path(tmp) / "unpacked"
            with tarfile.open(archive) as tar:
                _safe_extract(tar, staging)
            root = _find_manifest_root(staging)
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root), str(target))
        return cls.open(target)


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    dest.mkdir(parents=True)
    for member in tar.getmembers():
        path = (dest / member.name).resolve()
        if not str(path).startswith(str(dest.resolve()) + os.sep) and path != dest.resolve():
            raise BundleError(f"archive entry escapes the target directory: {member.name}")
        if member.issym() or member.islnk():
            raise BundleError(f"archive contains a link: {member.name}")
    tar.extractall(dest)  # noqa: S202 - members checked above


def _find_manifest_root(staging: Path) -> Path:
    if (staging / "manifest.json").is_file():
        return staging
    children = [p for p in staging.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / "manifest.json").is_file():
        return children[0]
    raise BundleError("archive has no manifest.json at its top level")
