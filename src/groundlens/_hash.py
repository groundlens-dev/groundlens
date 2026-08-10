"""Canonical serialisation and the content hash.

``sha256`` is what makes a published finding citable: quote the hash
and anyone can recompute it and see whether they got your result.

It covers the structural fields and the numeral supports exactly, and rounds
lexical supports to six decimals before hashing. That is the honest boundary.
The numeral channel is a Decimal comparison and is bit-reproducible anywhere.
The lexical channel is a float32 cosine and is not bit-identical between x86
and Apple Silicon -- so the hash is defined on a rounding of it, and we say so
instead of claiming a reproducibility we cannot deliver.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from groundlens._types import Anchor

#: Decimal places lexical supports are rounded to before hashing. 1e-6 is
#: comfortably wider than cross-platform float32 drift and far narrower than
#: any difference a reader would care about.
SUPPORT_PRECISION = 6


def canonical_json(payload: Any) -> str:
    """Deterministic JSON. Sorted keys, no incidental whitespace, UTF-8 preserved."""
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def anchor_payload(anchor: Anchor) -> dict[str, Any]:
    support = (
        round(anchor.support, SUPPORT_PRECISION) if anchor.kind == "lexical" else anchor.support
    )
    return {
        "text": anchor.text,
        "span": list(anchor.span),
        "kind": anchor.kind,
        "support": support,
        "value": anchor.value,
        "evidence_id": anchor.evidence_id,
        "evidence_text": anchor.evidence_text,
        "evidence_span": list(anchor.evidence_span) if anchor.evidence_span else None,
        "notes": list(anchor.notes),
    }


def content_hash(
    *,
    anchors: tuple[Anchor, ...],
    k: int,
    encoder_id: str,
    warnings: tuple[str, ...],
) -> str:
    """Hash of everything a reader would need to agree that they reproduced you."""
    return sha256_text(
        canonical_json(
            {
                "version": 1,
                "encoder_id": encoder_id,
                "k": k,
                "anchors": [anchor_payload(a) for a in anchors],
                "warnings": list(warnings),
            }
        )
    )
