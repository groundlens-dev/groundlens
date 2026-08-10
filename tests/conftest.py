"""Test doubles.

The whole library is testable without a model download. ``FakeEncoder`` is a
pure-Python, dependency-free, fully deterministic :class:`~groundlens.Encoder`:

* it pre-tokenises the way a BERT-family tokenizer does (whitespace, then
  punctuation split off), so ``10,000`` becomes three tokens and the alignment
  code has to cope with a word boundary the library and the encoder disagree on;
* it splits long words into <=4-character subwords, so multi-token words are
  exercised;
* it embeds char trigrams into a fixed-dimension vector, so identical strings
  reach 1.0, related strings land in between, and unrelated strings sit low.

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

    def _pieces(self, text: str) -> list[tuple[int, int, int]]:
        """(start, end, word_index) for every token. Shared by both protocol methods
        so a window can never disagree with the plan that produced it."""
        out: list[tuple[int, int, int]] = []
        for word_index, match in enumerate(_PRETOK.finditer(text)):
            start, end = match.span()
            for offset in range(0, end - start, _SUBWORD):
                out.append((start + offset, min(start + offset + _SUBWORD, end), word_index))
        return out

    def token_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((a, b) for a, b, _ in self._pieces(text))

    def encode_window(self, text: str) -> WindowEncoding:
        pieces = self._pieces(text)
        if len(pieces) > self._max_tokens:
            msg = f"window of {len(pieces)} tokens exceeds max_tokens={self._max_tokens}"
            raise AssertionError(msg)
        return WindowEncoding(
            token_spans=tuple((a, b) for a, b, _ in pieces),
            word_ids=tuple(w for _, _, w in pieces),
            vectors=[_embed(text[a:b]) for a, b, _ in pieces],
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

# Every content word of these answers also appears in INVOICE_CONTEXT, on
# purpose. FakeEncoder has no semantics -- it puts identical strings at 1.0
# and everything else near 0.0 -- so a fixture containing paraphrase would put
# innocent words on the floor and mask the numeral. Keeping the vocabulary
# covered isolates exactly one variable: the number.
#
# (That masking is not a quirk of the fake. It is the real failure mode of the
# pure-geometry variant of this metric: the floor was always occupied by
# innocent words while the wrong number sat comfortably above it. Which is why
# numbers are decided by arithmetic and not by similarity.)
INVOICE_GROUNDED = (
    "The invoice total amount due is 10,000 dollars payable within 30 days of delivery."
)

INVOICE_PERTURBED = INVOICE_GROUNDED.replace("10,000", "1,000")
INVOICE_REFORMATTED = INVOICE_GROUNDED.replace("10,000", "10000")
