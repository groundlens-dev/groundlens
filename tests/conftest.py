"""Test doubles.

The whole library is testable without a model download. ``FakeEncoder`` is a
pure-Python, dependency-free, fully deterministic :class:`~groundlens.Encoder`:

* it pre-tokenises the way a BERT-family tokenizer does (whitespace, then
  punctuation split off), so ``10,000`` becomes three tokens and the alignment
  code has to cope with a word boundary the library and the encoder disagree on;
* it splits long words into <=4-character subwords, so multi-token words are
  exercised;
* it embeds char trigrams into a fixed-dimension vector, so identical strings
  score 1.0, related strings score in between, and unrelated strings score low.

That is enough to test every decision the library makes. It is not enough to
reproduce a published number -- for that, see ``scripts/verify_encoder.py``.
"""

from __future__ import annotations

import hashlib
import math
import re

import pytest

from groundlens._types import WindowEncoding

_DIM = 64
_PRETOK = re.compile(r"\w+|[^\w\s]")
_SUBWORD = 4


def _unit(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _embed(text: str) -> list[float]:
    """Deterministic char-trigram hash embedding. Same text -> same vector, always."""
    key = f" {text.lower()} "
    vec = [0.0] * _DIM
    for i in range(len(key) - 2):
        tri = key[i : i + 3]
        digest = hashlib.sha256(tri.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % _DIM
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[idx] += sign
    return _unit(vec)


class FakeEncoder:
    """A deterministic stand-in for a sentence encoder."""

    def __init__(self, max_tokens: int = 16) -> None:
        self._max_tokens = max_tokens

    @property
    def id(self) -> str:
        return f"fake-trigram-{_DIM}@v1"

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def encode_window(self, text: str) -> WindowEncoding:
        spans: list[tuple[int, int]] = []
        word_ids: list[int | None] = []
        vectors: list[list[float]] = []
        for word_index, match in enumerate(_PRETOK.finditer(text)):
            start, end = match.span()
            piece = match.group(0)
            for offset in range(0, len(piece), _SUBWORD):
                sub_start = start + offset
                sub_end = min(start + offset + _SUBWORD, end)
                spans.append((sub_start, sub_end))
                word_ids.append(word_index)
                vectors.append(_embed(text[sub_start:sub_end]))
        return WindowEncoding(
            token_spans=tuple(spans),
            word_ids=tuple(word_ids),
            vectors=vectors,
        )


@pytest.fixture()
def encoder() -> FakeEncoder:
    return FakeEncoder()


@pytest.fixture()
def tiny_encoder() -> FakeEncoder:
    """max_tokens=8 -- forces windowing on almost any real sentence."""
    return FakeEncoder(max_tokens=8)


INVOICE_CONTEXT = (
    "According to the invoice, the total amount due is 10,000 dollars, "
    "payable within 30 days of delivery."
)

INVOICE_GROUNDED = (
    "The document is an invoice describing the commercial terms of the delivery. "
    "It specifies the payment schedule, notes that payment is expected within 30 days "
    "of delivery, and states a total amount due of 10,000 dollars for the goods received."
)

INVOICE_PERTURBED = INVOICE_GROUNDED.replace("10,000", "1,000")
INVOICE_REFORMATTED = INVOICE_GROUNDED.replace("10,000", "10000")
