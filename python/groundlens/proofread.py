"""``proofread()``: the groundlens 3.x API, kept.

Same signature, same :class:`Proofread` and :class:`Anchor` types, same
numeral semantics (a number is equal or it is wrong, support exactly 1.0 or
0.0, ambiguous numerals keep every reading, the question never adds
support). The numeral channel now runs inside the GLV engine and is checked
against a golden file produced by groundlens 3.1.

In this development build only the numeral channel is scored. Passing an
``encoder`` raises until the lexical channel is ported (the release gate of
4.0.0). Use :func:`groundlens.verify` for the 4.0 pipeline with policies and
signed records.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from typing import Any

from groundlens import _engine
from groundlens._request import build_request
from groundlens._types import Anchor, Encoder, Evidence, Proofread

ContextArg = str | Sequence[str] | Sequence[tuple[str, str]] | Sequence[Evidence] | Sequence[object]

LEXICAL_PENDING = (
    "lexical channel not available in this build: only numerals were scored. "
    "Words return with groundlens 4.0.0."
)


def adaptive_k(n: int) -> int:
    """``k=0`` selects this: one weak word decides a short answer, a small set of
    them decides a long one."""
    return max(1, min(4, math.ceil(0.15 * n)))


def as_evidence(context: ContextArg) -> tuple[Evidence, ...]:
    """Accept the shapes people actually have, but keep ids wherever they exist."""
    if isinstance(context, str):
        return (Evidence(id="ctx-0", text=context),)
    out: list[Evidence] = []
    for index, item in enumerate(context):
        if isinstance(item, Evidence):
            out.append(item)
        elif isinstance(item, str):
            out.append(Evidence(id=f"ctx-{index}", text=item))
        elif isinstance(item, tuple) and len(item) == 2:
            identifier, text = item
            out.append(Evidence(id=str(identifier), text=str(text)))
        else:
            msg = (
                "context items must be str, (id, text) tuples or Evidence; "
                f"got {type(item).__name__} at position {index}"
            )
            raise TypeError(msg)
    return tuple(out)


def proofread(
    answer: str,
    context: ContextArg,
    *,
    encoder: Encoder | None = None,
    k: int = 1,
    locale: str = "und",
    max_anchors: int = 2048,
    question: str | None = None,
) -> Proofread:
    """Proofread ``answer`` against its sources and return where to look.

    Numerals are decided by arithmetic: support is exactly 1.0 or 0.0. There
    is no verdict in the result. See groundlens 3.x documentation for the
    full contract; it is unchanged.
    """
    if encoder is not None:
        raise NotImplementedError(LEXICAL_PENDING)

    evidences = as_evidence(context)
    request = build_request(
        answer=answer,
        evidence=[(e.id, e.text) for e in evidences],
        question=question,
        locale=locale,
        units=False,
    )
    record = json.loads(_engine.verify_json(request))
    prepared = json.loads(_engine.prepare_json(request))

    warnings: list[str] = [LEXICAL_PENDING]
    if not evidences or not any(e.text for e in evidences):
        warnings.append("no context supplied; every word will read as unsupported")

    numeric_claims = [c for c in prepared["claims"] if c["kind"] == "numeric"]
    # The engine indexes bytes of the normalised UTF-8 text; the 3.x contract
    # indexes characters. Convert once per text.
    answer_chars = _byte_to_char(prepared["answer"])
    source_chars = {s["id"]: _byte_to_char(s["text"]) for s in prepared["sources"]}
    if len(numeric_claims) > max_anchors:
        msg = (
            f"answer has {len(numeric_claims)} scoring words, above max_anchors={max_anchors}. "
            "Raise max_anchors deliberately, or proofread the answer in sections."
        )
        raise ValueError(msg)

    by_claim: dict[str, dict[str, Any]] = {
        e["claim_id"]: e
        for e in record["content"]["graph"]["evidence"]
        if e["verifier_id"] == "groundlens.numeric"
    }

    anchors: list[Anchor] = []
    for claim in numeric_claims:
        ev = by_claim.get(claim["id"])
        receipt = ev.get("receipt", {}) if ev else {}
        span = receipt.get("source_span")
        supported = bool(ev) and ev["result"] == "supported"
        src_chars = source_chars.get(receipt.get("source_id") or "", None)
        anchors.append(
            Anchor(
                text=claim["text"],
                span=(answer_chars[claim["span"]["start"]], answer_chars[claim["span"]["end"]]),
                kind="numeral",
                support=1.0 if supported else 0.0,
                value=claim["attributes"].get("canonical"),
                evidence_id=receipt.get("source_id"),
                evidence_text=receipt.get("source_text"),
                evidence_span=(src_chars[span["start"]], src_chars[span["end"]]) if span and src_chars else None,
                notes=tuple(receipt.get("notes", ())),
            )
        )

    marked = anchors
    resolved_k = adaptive_k(len(marked)) if k == 0 else max(1, k)
    resolved_k = min(resolved_k, len(marked)) if marked else 0

    def rank(anchor: Anchor) -> tuple[float, int, tuple[int, int]]:
        return (anchor.support, 0 if anchor.kind == "numeral" else 1, anchor.span)

    weakest = tuple(sorted(marked, key=rank)[:resolved_k])
    value = sum(a.support for a in weakest) / resolved_k if resolved_k else 1.0

    return Proofread(
        floor=value,
        k=resolved_k,
        weakest=weakest,
        anchors=tuple(anchors),
        n_marked=len(marked),
        n_numeral=len(marked),
        encoder_id="none",
        sha256=_content_hash(anchors, resolved_k, warnings),
        warnings=tuple(warnings),
    )


def _byte_to_char(text: str) -> list[int]:
    """Map every UTF-8 byte offset of ``text`` to a character offset."""
    table = [0] * (len(text.encode("utf-8")) + 1)
    b = 0
    for i, ch in enumerate(text):
        n = len(ch.encode("utf-8"))
        for k in range(n):
            table[b + k] = i
        b += n
    table[b] = len(text)
    return table


def _content_hash(anchors: Sequence[Anchor], k: int, warnings: Sequence[str]) -> str:
    """Same canonical form as groundlens 3.x ``_hash.content_hash``."""
    payload = {
        "version": 1,
        "encoder_id": "none",
        "k": k,
        "anchors": [
            {
                "text": a.text,
                "span": list(a.span),
                "kind": a.kind,
                "support": a.support,
                "value": a.value,
                "evidence_id": a.evidence_id,
                "evidence_text": a.evidence_text,
                "evidence_span": list(a.evidence_span) if a.evidence_span else None,
                "notes": list(a.notes),
            }
            for a in anchors
        ],
        "warnings": list(warnings),
    }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
