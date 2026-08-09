"""Declarative rule packs.

A rule pack is YAML. It is read, hashed and validated; it is never imported.
The reason is not aesthetic. A rule pack that is Python cannot be read,
diffed or approved by the compliance reviewer who is accountable for it, and
a version label that a human typed does not bind to behaviour. A content hash
does.

Typical use::

    from groundlens.packs import load_pack

    pack = load_pack("eu-retail-banking")
    pack.content_sha256      # what actually identifies this pack
    pack.requires_metadata   # absent keys are a FAIL, with no way to disable

:mod:`groundlens.packs.evaluate` is imported lazily so that loading and
hashing a pack does not require the rest of the control path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from groundlens.packs.loader import (
    ASSERT_KINDS,
    SEVERITIES,
    Pack,
    PackError,
    PackRule,
    load_pack,
    shipped_pack_names,
)
from groundlens.packs.predicates import (
    PredicateContext,
    PredicateEntry,
    PredicateError,
    PredicateRegistry,
)

if TYPE_CHECKING:
    from groundlens.packs.evaluate import evaluate_pack, missing_metadata_findings

__all__ = [
    "ASSERT_KINDS",
    "SEVERITIES",
    "Pack",
    "PackError",
    "PackRule",
    "PredicateContext",
    "PredicateEntry",
    "PredicateError",
    "PredicateRegistry",
    "evaluate_pack",
    "load_pack",
    "missing_metadata_findings",
    "shipped_pack_names",
]

_LAZY: frozenset[str] = frozenset({"evaluate_pack", "missing_metadata_findings"})


def __getattr__(name: str) -> Any:
    """Resolve the evaluation entry points on first access."""
    if name in _LAZY:
        from groundlens.packs import evaluate as _evaluate

        return getattr(_evaluate, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
