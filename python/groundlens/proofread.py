"""``proofread()``: the groundlens 3.x API, kept.

Same signature, same :class:`Proofread` and :class:`Anchor` types, same
semantics. Numerals are decided by arithmetic (support exactly 1.0 or 0.0,
ambiguous numerals keep every reading, the question never adds support).
Words are anchored by contextual token similarity against a frozen encoder,
aligned by character-span overlap, read through overlapping windows, with
the floor rather than the mean as the aggregate. Both channels now run
inside the GLV engine and are checked against golden files produced by
groundlens 3.1 itself.

The encoder comes from a bundle (``groundlens bundle pull base``) instead
of from a Python object: that is what makes the number a record can point
at. Without a bundle, words are not scored and the result says so in
``warnings``.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from groundlens import _engine
from groundlens._request import build_request
from groundlens._types import Anchor, Evidence, Proofread
from groundlens.bundle import Bundle

ContextArg = str | Sequence[str] | Sequence[tuple[str, str]] | Sequence[Evidence] | Sequence[object]

NO_ENCODER = (
    "no bundle installed: only numerals were scored. Run `groundlens bundle pull base` "
    "to score words as well."
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
    bundle: Bundle | str | Path | None = None,
    encoder: object | None = None,
    k: int = 1,
    locale: str = "und",
    max_anchors: int = 2048,
    question: str | None = None,
) -> Proofread:
    """Proofread ``answer`` against its sources and return where to look.

    Args:
        answer: the model output to check.
        context: the retrieved sources. Pass ``(id, text)`` pairs so findings
            can name which source backed each word.
        bundle: a :class:`Bundle`, a bundle directory or a bundle name.
            ``None`` uses the installed ``base`` bundle when there is one.
        encoder: not supported any more. The encoder is the bundle's; pass
            ``bundle`` instead.
        k: how many of the weakest anchors the floor averages. ``1`` is the
            default. ``0`` selects :func:`adaptive_k`.
        locale: how this corpus writes numbers: ``"es"``, ``"en"``, ``"de"``...
        max_anchors: refuse answers longer than this many scoring words.
        question: what the model was asked. Never a source; anchors that echo
            it are noted.

    Returns:
        A :class:`Proofread`. There is no verdict in it.
    """
    if encoder is not None:
        raise TypeError(
            "proofread(encoder=...) is not supported by groundlens 4: the encoder comes from a "
            "bundle so records can name it by hash. Pass bundle=... or install one with "
            "`groundlens bundle pull base`."
        )

    evidences = as_evidence(context)
    bundle_arg = str(bundle.root) if isinstance(bundle, Bundle) else (str(bundle) if bundle else None)
    request = build_request(
        answer=answer,
        evidence=[(e.id, e.text) for e in evidences],
        question=question,
        locale=locale,
        units=False,
        bundle=bundle_arg,
    )
    record = json.loads(_engine.verify_json(request))
    prepared = json.loads(_engine.prepare_json(request))
    answer_text: str = prepared["answer"]

    encoder_id = "none"
    for v in record["content"]["graph"]["verifiers"]:
        if v["id"] == "groundlens.lexical":
            encoder_id = dict(v.get("artefacts", [])).get("encoder", "none")
    scored = encoder_id != "none"

    warnings: list[str] = list(_segmentation_warnings(answer_text))
    if not scored:
        warnings.append(NO_ENCODER)
    if not evidences or not any(e.text for e in evidences):
        warnings.append("no context supplied; every word will read as unsupported")

    claims = prepared["claims"]
    scoring = [c for c in claims if c["kind"] in ("numeric", "word")]
    if len(scoring) > max_anchors:
        msg = (
            f"answer has {len(scoring)} scoring words, above max_anchors={max_anchors}. "
            "Raise max_anchors deliberately, or proofread the answer in sections."
        )
        raise ValueError(msg)

    # The engine indexes bytes of the normalised UTF-8 text; the 3.x contract
    # indexes characters. Convert once per text.
    answer_chars = _byte_to_char(answer_text)
    source_chars = {s["id"]: _byte_to_char(s["text"]) for s in prepared["sources"]}

    evidence_by: dict[tuple[str, str], dict[str, Any]] = {
        (e["verifier_id"], e["claim_id"]): e for e in record["content"]["graph"]["evidence"]
    }
    question_words = _question_words(question, locale)

    anchors: list[Anchor] = []
    for claim in claims:
        span = (answer_chars[claim["span"]["start"]], answer_chars[claim["span"]["end"]])
        if claim["kind"] == "numeric":
            ev = evidence_by.get(("groundlens.numeric", claim["id"]))
            anchors.append(_numeral_anchor(claim, span, ev, source_chars))
        elif claim["kind"] == "word":
            ev = evidence_by.get(("groundlens.lexical", claim["id"]))
            anchors.append(_lexical_anchor(claim, span, ev, source_chars, question_words, scored=scored))
    for w in json.loads(_engine.segment_json(answer_text, locale)):
        if w["stopword"]:
            anchors.append(
                Anchor(
                    text=w["text"],
                    span=(answer_chars[w["start"]], answer_chars[w["end"]]),
                    kind="skipped",
                    support=1.0,
                    notes=("stopword",),
                )
            )
    anchors.sort(key=lambda a: a.span)

    marked = [a for a in anchors if a.kind == "numeral" or (a.kind == "lexical" and scored)]
    resolved_k = adaptive_k(len(marked)) if k == 0 else max(1, k)
    resolved_k = min(resolved_k, len(marked)) if marked else 0

    # A numeral at 0.0 is a proven mismatch; a word at 0.0 only found no
    # anchor. Numerals win ties, position breaks the rest.
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
        n_numeral=sum(1 for a in marked if a.kind == "numeral"),
        encoder_id=encoder_id,
        sha256=_content_hash(anchors, resolved_k, encoder_id, warnings),
        warnings=tuple(warnings),
    )


def _numeral_anchor(claim: dict, span: tuple[int, int], ev: dict | None, source_chars: dict) -> Anchor:
    receipt = ev.get("receipt", {}) if ev else {}
    sspan = receipt.get("source_span")
    src_chars = source_chars.get(receipt.get("source_id") or "")
    return Anchor(
        text=claim["text"],
        span=span,
        kind="numeral",
        support=1.0 if ev and ev["result"] == "supported" else 0.0,
        value=claim["attributes"].get("canonical"),
        evidence_id=receipt.get("source_id"),
        evidence_text=receipt.get("source_text"),
        evidence_span=(src_chars[sspan["start"]], src_chars[sspan["end"]]) if sspan and src_chars else None,
        notes=tuple(receipt.get("notes", ())),
    )


def _lexical_anchor(
    claim: dict,
    span: tuple[int, int],
    ev: dict | None,
    source_chars: dict,
    question_words: frozenset[str],
    *,
    scored: bool,
) -> Anchor:
    if not scored:
        notes = ["not_scored"]
        if claim["text"].casefold() in question_words:
            notes.append("echoes_question")
        return Anchor(text=claim["text"], span=span, kind="lexical", support=0.0, notes=tuple(notes))
    receipt = ev.get("receipt", {}) if ev else {}
    sspan = receipt.get("source_span")
    src_chars = source_chars.get(receipt.get("source_id") or "")
    return Anchor(
        text=claim["text"],
        span=span,
        kind="lexical",
        support=float(ev["score"]) if ev else 0.0,
        evidence_id=receipt.get("source_id"),
        evidence_text=receipt.get("source_text"),
        evidence_span=(src_chars[sspan["start"]], src_chars[sspan["end"]]) if sspan and src_chars else None,
        notes=tuple(receipt.get("notes", ())),
    )


def _question_words(question: str | None, locale: str) -> frozenset[str]:
    if not question or not question.strip():
        return frozenset()
    text = _engine.normalise(question)
    return frozenset(w["text"].casefold() for w in json.loads(_engine.segment_json(text, locale)) if not w["stopword"])


_UNSEGMENTED_LIMIT = 0.30


def _segmentation_warnings(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    unsegmented = sum(1 for ch in text if _is_unsegmented(ch))
    if unsegmented / len(text) > _UNSEGMENTED_LIMIT:
        return (
            "answer is largely in an unsegmented script (CJK/Thai); whitespace "
            "segmentation does not apply and these marks should not be relied on",
        )
    return ()


def _is_unsegmented(ch: str) -> bool:
    o = ord(ch)
    return 0x3000 <= o <= 0x9FFF or 0x0E00 <= o <= 0x0E7F or 0xAC00 <= o <= 0xD7AF


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


def _content_hash(anchors: Sequence[Anchor], k: int, encoder_id: str, warnings: Sequence[str]) -> str:
    """Same canonical form as groundlens 3.x ``_hash.content_hash``."""
    payload = {
        "version": 1,
        "encoder_id": encoder_id,
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
