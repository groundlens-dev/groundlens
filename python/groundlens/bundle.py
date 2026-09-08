"""A bundle is everything a verification needs, in one directory, with
checksums: models, tokenizers, calibrations, rules, policies.

Nothing in ``verify()`` ever fetches a bundle. Fetching is a separate,
explicit action so the engine can run in an isolated environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from groundlens import _engine


class BundleError(RuntimeError):
    """A manifest is missing or an artefact hash does not match."""


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

    @classmethod
    def pull(cls, name: str = "reference", *, into: str | Path | None = None) -> Bundle:
        """Fetch a published bundle. Not available in this development build:
        the reference bundle ships with 4.0.0 together with the lexical
        channel. Copy a bundle directory by hand and use ``Bundle.open``."""
        raise NotImplementedError(
            "Bundle.pull is not available in this build. Copy a bundle directory into place and call Bundle.open(path)."
        )
