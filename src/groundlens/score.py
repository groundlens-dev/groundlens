"""The metric.

Two channels, and the whole design is in the split between them.

**Words are anchored by meaning.** A word's support is the highest cosine
similarity it reaches against any word of the sources. A well-grounded word
finds a strong anchor somewhere; a word with nothing behind it does not.

**Numbers are anchored by arithmetic.** A number is not similar to another
number. It is equal or it is wrong. Support is exactly 1.0 or exactly 0.0, and
similarity is not allowed to vote.

**The score is the floor, not the average.** Every token-similarity metric in
the literature aggregates by the mean, and the mean is precisely where a
single-token error goes to die: a sixty-word answer with one wrong digit has a
mean support of about 0.79, which looks fine, and a weakest anchor of 0.00,
which is an alarm.

And the output is not a verdict. It is a short ranked list of words, each one
printed next to the source word it lost to.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal

from groundlens._align import TokenVectors, best_anchor, embed, tokens_overlapping
from groundlens._hash import profile_hash
from groundlens._numerals import Numeral, find_numerals
from groundlens._numerals import locale as locale_profile
from groundlens._text import normalised
from groundlens._types import Anchor, AnchorProfile, Encoder, Evidence
from groundlens._words import Unit, segment, segmentation_warnings


#: ``k=0`` selects this: one weak word decides a short answer, a small set of
#: them decides a long one. ``k=1`` is the default because it is the only
#: variant whose output a human can act on without a second explanation.
def adaptive_k(n: int) -> int:
    return max(1, min(4, math.ceil(0.15 * n)))


#: An ``(id, text)`` pair has exactly two members.
_ID_TEXT_PAIR = 2

ContextArg = str | Sequence[str] | Sequence[tuple[str, str]] | Sequence[Evidence] | Sequence[object]


def as_evidence(context: ContextArg) -> tuple[Evidence, ...]:
    """Accept the shapes people actually have, but keep ids wherever they exist.

    Without an id a finding cannot say *which source* backed a word, and "which
    source backed this" is the question a reviewer actually asks.
    """
    if isinstance(context, str):
        return (Evidence(id="ctx-0", text=context),)
    out: list[Evidence] = []
    for index, item in enumerate(context):
        if isinstance(item, Evidence):
            out.append(item)
        elif isinstance(item, str):
            out.append(Evidence(id=f"ctx-{index}", text=item))
        elif isinstance(item, tuple) and len(item) == _ID_TEXT_PAIR:
            identifier, text = item
            out.append(Evidence(id=str(identifier), text=str(text)))
        else:
            msg = (
                "context items must be str, (id, text) tuples or Evidence; "
                f"got {type(item).__name__} at position {index}"
            )
            raise TypeError(msg)
    return tuple(out)


def _nearest_numeral(
    value: Decimal,
    context_numerals: Sequence[tuple[str, Numeral]],
) -> tuple[str, Numeral, Decimal] | None:
    """The source number closest to ``value``. This is the receipt on a wrong number.

    Distance is *relative*, not absolute, and that choice matters. Against a
    source saying "10,000 dollars payable within 30 days", a wrong "1,000" is
    970 away from 30 and 9,000 away from 10,000 -- so absolute distance points
    the reviewer at the deadline, which is useless. Relative distance puts
    10,000 at 0.90 and 30 at 0.97 and points at the number a digit was actually
    dropped from, which is the one a human wants to see.
    """
    best: tuple[str, Numeral, Decimal] | None = None
    for evidence_id, numeral in context_numerals:
        for reading in numeral.readings:
            scale = max(abs(reading), abs(value), Decimal(1))
            distance = abs(reading - value) / scale
            if best is None or distance < best[2]:
                best = (evidence_id, numeral, distance)
    return best


def _numeral_anchor(
    unit: Unit,
    context_values: frozenset[Decimal],
    context_numerals: Sequence[tuple[str, Numeral]],
) -> Anchor:
    numeral = unit.numeral
    assert numeral is not None
    notes = list(unit.notes)
    if numeral.ambiguous and "numeral_ambiguous" not in notes:
        notes.append("numeral_ambiguous")

    supported = any(reading in context_values for reading in numeral.readings)
    evidence_id = evidence_text = None
    evidence_span = None

    match = _nearest_numeral(numeral.readings[0], context_numerals)
    if match is not None:
        evidence_id, source_numeral, _ = match
        if supported:
            # Prefer the source numeral that actually carries the same value.
            for candidate_id, candidate in context_numerals:
                if any(r in context_values and r in numeral.readings for r in candidate.readings):
                    evidence_id, source_numeral = candidate_id, candidate
                    break
        evidence_text = source_numeral.text
        evidence_span = source_numeral.span

    return Anchor(
        text=unit.text,
        span=unit.span,
        kind="numeral",
        support=1.0 if supported else 0.0,
        value=numeral.canonical,
        evidence_id=evidence_id,
        evidence_text=evidence_text,
        evidence_span=evidence_span,
        notes=tuple(notes),
    )


def _lexical_anchor(
    unit: Unit,
    answer_tokens: TokenVectors,
    context_tokens: Sequence[tuple[Evidence, TokenVectors]],
) -> Anchor:
    # Rule 1 of _align: no word is ever silently dropped. A word that reaches
    # the scorer and produces no support is the failure this library exists to
    # prevent -- because the score is a floor, a missing word can only push it
    # up, and a truncated long answer then looks better grounded than it is.
    #
    # Note what is checked: whether the word aligned to a token of the *answer*.
    # An answer word with no answer token means the encoder adapter is broken,
    # and that is an error. Having no context at all is a different thing --
    # support 0.0 is then the correct and honest answer, and score() has already
    # attached a warning saying so.
    if not tokens_overlapping(unit.span, answer_tokens):
        msg = (
            f"word {unit.text!r} at {unit.span} aligned to no encoder token. "
            "This would silently raise the score; refusing to continue."
        )
        raise RuntimeError(msg)

    best_support = 0.0
    best_id: str | None = None
    best_text: str | None = None
    best_span: tuple[int, int] | None = None

    for evidence, tokens in context_tokens:
        found = best_anchor(unit.span, answer_tokens, tokens)
        if found is None:
            continue
        support, token_index = found
        if best_id is None or support > best_support:
            best_support = support
            best_id = evidence.id
            best_span = tokens.spans[token_index]
            best_text = evidence.text[best_span[0] : best_span[1]]

    return Anchor(
        text=unit.text,
        span=unit.span,
        kind="lexical",
        support=best_support,
        evidence_id=best_id,
        evidence_text=best_text,
        evidence_span=best_span,
        notes=unit.notes,
    )


def score(
    answer: str,
    context: ContextArg,
    *,
    encoder: Encoder,
    k: int = 1,
    locale: str = "und",
    max_anchors: int = 2048,
) -> AnchorProfile:
    """Score ``answer`` against ``context`` and return where to look.

    Args:
        answer: the model output to check.
        context: the retrieved sources. Pass ``(id, text)`` pairs so findings
            can name which source backed each word.
        encoder: any :class:`~groundlens.Encoder`. Use
            :class:`~groundlens.SentenceTransformerEncoder` for the reference one.
        k: how many of the weakest anchors the score averages. ``1`` is the
            default and the recommended setting. ``0`` selects
            :func:`adaptive_k`, which is what the published benchmark used.
        locale: how this corpus writes numbers -- ``"es"``, ``"en"``, ``"de"``...
            Leave as ``"und"`` and ambiguous numerals keep every valid reading.
        max_anchors: refuse answers longer than this many scoring words rather
            than quietly taking a very long time.

    Returns:
        An :class:`~groundlens.AnchorProfile`. There is no verdict in it.
    """
    profile = locale_profile(locale)
    answer_text = normalised(answer)
    evidences = tuple(
        Evidence(id=item.id, text=normalised(item.text)) for item in as_evidence(context)
    )

    warnings = list(segmentation_warnings(answer_text))
    if not evidences or not any(e.text for e in evidences):
        warnings.append("no context supplied; every word will score as unsupported")

    units = segment(answer_text, profile)
    scoring = [u for u in units if u.kind != "skipped"]
    if len(scoring) > max_anchors:
        msg = (
            f"answer has {len(scoring)} scoring words, above max_anchors={max_anchors}. "
            "Raise max_anchors deliberately, or score the answer in sections."
        )
        raise ValueError(msg)

    context_values = frozenset(
        reading
        for evidence in evidences
        for numeral in find_numerals(evidence.text, profile)
        for reading in numeral.readings
    )
    context_numerals: list[tuple[str, Numeral]] = [
        (evidence.id, numeral)
        for evidence in evidences
        for numeral in find_numerals(evidence.text, profile)
    ]

    needs_geometry = any(u.kind == "lexical" for u in scoring)
    answer_tokens = embed(answer_text, encoder) if needs_geometry else TokenVectors((), ())
    context_tokens: list[tuple[Evidence, TokenVectors]] = (
        [(e, embed(e.text, encoder)) for e in evidences if e.text] if needs_geometry else []
    )

    anchors: list[Anchor] = []
    for unit in units:
        if unit.kind == "skipped":
            anchors.append(
                Anchor(
                    text=unit.text, span=unit.span, kind="skipped", support=1.0, notes=unit.notes
                )
            )
        elif unit.kind == "numeral":
            anchors.append(_numeral_anchor(unit, context_values, context_numerals))
        else:
            anchors.append(_lexical_anchor(unit, answer_tokens, context_tokens))

    scored = [a for a in anchors if a.kind != "skipped"]
    resolved_k = adaptive_k(len(scored)) if k == 0 else max(1, k)
    resolved_k = min(resolved_k, len(scored)) if scored else 0

    # A numeral at 0.0 and a word at 0.0 are not the same kind of zero, and
    # ranking them equally buries the finding that matters. A numeral at 0.0 is
    # a *proven* mismatch: arithmetic says this value is not in the sources. A
    # word at 0.0 only means it found no lexical anchor, which is ordinary for
    # honest paraphrase -- "commercial" and "consistent" score low in a
    # perfectly grounded answer. So numerals win ties, and position breaks the
    # rest, because sort stability must not vary between interpreters.
    def rank(anchor: Anchor) -> tuple[float, int, tuple[int, int]]:
        return (anchor.support, 0 if anchor.kind == "numeral" else 1, anchor.span)

    weakest = tuple(sorted(scored, key=rank)[:resolved_k])
    value = sum(a.support for a in weakest) / resolved_k if resolved_k else 1.0

    return AnchorProfile(
        score=value,
        k=resolved_k,
        weakest=weakest,
        anchors=tuple(anchors),
        n_scored=len(scored),
        n_numeral=sum(1 for a in scored if a.kind == "numeral"),
        encoder_id=encoder.id,
        profile_sha256=profile_hash(
            anchors=tuple(anchors),
            k=resolved_k,
            encoder_id=encoder.id,
            warnings=tuple(warnings),
        ),
        warnings=tuple(warnings),
    )
