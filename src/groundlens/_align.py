"""Windowing and word-to-token alignment.

This is the highest-risk module in the library, and it is the one that was
wrong in the notebook this code replaces.

The notebook chunked text at a hard 384-token cap and its own run log contains
a warning that a 401-token sequence exceeded it. Tokens past the cap get no
embedding, so the words they belong to get no support. Because the floor is a
*floor* over the weakest anchors, silently dropping words can only push the
it **up**. Long answers were therefore read as better grounded than they
were -- and the benchmark those numbers came from was a long-answer set.

Two rules follow, and both are enforced by tests rather than by review:

1. Every scoring unit gets a support value. None is dropped, ever. If a word
   cannot be aligned to a token, that is a hard error, not a shrug.
2. Windows overlap by a stride, and a word's support is the maximum over every
   window it appears in -- so a word sitting on a window boundary is measured
   against the context, not against an accident of where the cut landed.

Alignment is by **character-span overlap**, not by the encoder's ``word_ids``.
The library segments its own words (``10,000`` is one word) and encoders do not
agree with that (a BERT pre-tokenizer makes it three). Overlap is the only
mapping that survives that disagreement.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundlens._types import Encoder, Span

#: Fraction of a window that is re-read by the next one. A word within
#: STRIDE_RATIO of a boundary is guaranteed to appear whole in some window.
STRIDE_RATIO = 0.5


@dataclass(frozen=True, slots=True)
class Window:
    """One slice of text, small enough to encode, with its offset in the whole."""

    offset: int
    text: str
    first_token: int
    last_token: int


def plan_windows(text: str, encoder: Encoder) -> tuple[Window, ...]:
    """Cut ``text`` into overlapping windows that each fit the encoder.

    Cuts land on token boundaries, so no window ever splits a token. An empty
    text yields no windows, which callers must handle rather than assume.
    """
    if not text:
        return ()
    spans = encoder.token_spans(text)
    if not spans:
        return ()

    limit = max(1, encoder.max_tokens)
    if len(spans) <= limit:
        return (Window(offset=0, text=text, first_token=0, last_token=len(spans) - 1),)

    stride = max(1, int(limit * STRIDE_RATIO))
    windows: list[Window] = []
    start = 0
    while start < len(spans):
        end = min(start + limit, len(spans)) - 1
        begin_char = spans[start][0]
        end_char = spans[end][1]
        windows.append(
            Window(
                offset=begin_char,
                text=text[begin_char:end_char],
                first_token=start,
                last_token=end,
            )
        )
        if end == len(spans) - 1:
            break
        start += stride
    return tuple(windows)


@dataclass(frozen=True, slots=True)
class TokenVectors:
    """Every token of one text, with global char spans and L2-normalised vectors."""

    spans: tuple[Span, ...]
    vectors: tuple[tuple[float, ...], ...]

    def __len__(self) -> int:
        return len(self.spans)


def embed(text: str, encoder: Encoder) -> TokenVectors:
    """Encode ``text`` through as many windows as it takes, in global coordinates.

    A token appearing in two overlapping windows is kept twice. That is
    deliberate: the two copies have slightly different vectors because their
    context differs, and taking the max over both is what makes a word's support
    independent of where the window boundary happened to fall.
    """
    spans: list[Span] = []
    vectors: list[tuple[float, ...]] = []
    for window in plan_windows(text, encoder):
        encoded = encoder.encode_window(window.text)
        if len(encoded.token_spans) != len(encoded.vectors):
            msg = (
                f"encoder {encoder.id!r} returned {len(encoded.token_spans)} spans "
                f"and {len(encoded.vectors)} vectors; they must match"
            )
            raise ValueError(msg)
        for (local_start, local_end), vector in zip(
            encoded.token_spans, encoded.vectors, strict=True
        ):
            spans.append((window.offset + local_start, window.offset + local_end))
            vectors.append(tuple(vector))
    return TokenVectors(spans=tuple(spans), vectors=tuple(vectors))


def tokens_overlapping(span: Span, tokens: TokenVectors) -> list[int]:
    """Indices of every token whose characters intersect ``span``."""
    start, end = span
    return [i for i, (a, b) in enumerate(tokens.spans) if a < end and b > start]


def _max_similarity_pure(
    rows: list[int],
    answer: TokenVectors,
    context: TokenVectors,
    cols: list[int],
) -> tuple[float, int]:
    """Best (similarity, context token index) over answer tokens ``rows``."""
    best = -1.0
    best_j = -1
    for i in rows:
        a = answer.vectors[i]
        for j in cols:
            c = context.vectors[j]
            dot = 0.0
            for x, y in zip(a, c, strict=True):
                dot += x * y
            if dot > best:
                best = dot
                best_j = j
    return best, best_j


def _max_similarity_numpy(
    rows: list[int],
    answer: TokenVectors,
    context: TokenVectors,
    cols: list[int],
) -> tuple[float, int] | None:
    """Same result, vectorised. Returns None when numpy is unavailable."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - exercised by the no-dependencies CI job
        return None
    a = np.asarray([answer.vectors[i] for i in rows], dtype=np.float32)
    c = np.asarray([context.vectors[j] for j in cols], dtype=np.float32)
    sims = a @ c.T
    flat = int(sims.argmax())
    return float(sims.flat[flat]), cols[int(flat % sims.shape[1])]


def scorable_columns(text: str, tokens: TokenVectors) -> tuple[int, ...]:
    """Context tokens worth anchoring to: at least one alphanumeric character.

    A period or a stray quote also gets a contextual vector, and on a short
    span it can win the max by accident. A support built on one is noise, and
    a receipt saying the nearest thing to your weakest word is a full stop
    helps nobody. Punctuation-only tokens are therefore excluded from the
    search. If a source contains nothing else, callers fall back to the full
    set, because support 0.0-by-filtering would be a lie of a different kind.
    """
    return tuple(
        j for j, (a, b) in enumerate(tokens.spans) if any(ch.isalnum() for ch in text[a:b])
    )


def best_anchor(
    span: Span,
    answer: TokenVectors,
    context: TokenVectors,
    candidate_cols: tuple[int, ...] | None = None,
) -> tuple[float, int] | None:
    """Support for the word at ``span``, and which context token gave it.

    Returns ``None`` only when the word maps to no token at all -- which the
    caller must treat as an error, because a word that reaches the metric and
    produces no support is exactly the silent drop this module exists to stop.
    """
    rows = tokens_overlapping(span, answer)
    if not rows or len(context) == 0:
        return None
    cols = list(candidate_cols) if candidate_cols else list(range(len(context)))
    vectorised = _max_similarity_numpy(rows, answer, context, cols)
    similarity, index = (
        vectorised if vectorised is not None else _max_similarity_pure(rows, answer, context, cols)
    )
    # Cosine of L2-normalised vectors lives in [-1, 1]; support is reported in
    # [0, 1] because a negative similarity and a zero one mean the same thing
    # here: nothing in the sources anchors this word.
    return max(0.0, min(1.0, similarity)), index
