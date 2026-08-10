"""Public data types and the encoder seam.

Nothing in this module imports numpy, torch or transformers. The encoder is a
Protocol so the whole library is testable without downloading a model, and so a
user can swap in their own retrieval encoder.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Span = tuple[int, int]

AnchorKind = Literal["lexical", "numeral", "skipped"]

#: Reason codes attachable to an anchor. Kept closed so they can be asserted on.
NOTE_CODES = frozenset(
    {
        "numeral_ambiguous",  # numeral had >1 valid reading; scored on the best of them
        "numeral_unparsed",  # looked numeric, could not be parsed; fell back to lexical
        "window_boundary",  # word straddles a window edge; support is the max over windows
        "stopword",  # excluded from scoring
        "no_alpha",  # punctuation-only token, excluded from scoring
        "single_digit",  # bare 1-digit numeral, treated lexically (enumerators)
    }
)


@dataclass(frozen=True, slots=True)
class Anchor:
    """One word of the answer and the best support it found in the sources."""

    text: str
    """The word, verbatim from the NFKC-normalised answer."""

    span: Span
    """Character offsets into the NFKC-normalised answer."""

    kind: AnchorKind
    """`numeral` words are decided by arithmetic, `lexical` words by geometry."""

    support: float
    """0.0-1.0. Exactly 0.0 or 1.0 for numerals -- a number is equal or it is wrong."""

    value: str | None = None
    """Canonical decimal string, for numerals only."""

    evidence_id: str | None = None
    """Which source supplied the best support."""

    evidence_text: str | None = None
    """The source word that supplied it. This is the receipt."""

    evidence_span: Span | None = None
    """Character offsets into that source."""

    notes: tuple[str, ...] = ()

    def receipt(self) -> str:
        """One line a human can act on."""
        if self.evidence_text is None:
            return f"{self.text}\tsupport {self.support:.2f}\tno anchor found"
        where = self.evidence_id or "source"
        return (
            f"{self.text}\tsupport {self.support:.2f}\tnearest in {where}: {self.evidence_text!r}"
        )


@dataclass(frozen=True, slots=True)
class AnchorProfile:
    """The result of scoring one answer against its sources.

    There is deliberately no ``decision`` field and no default threshold. At 95%
    hallucination recall no published method -- including this one -- reaches a
    false-positive rate below 0.65 on any benchmark we have measured. Shipping a
    threshold would ship a control that escalates most correct answers. Use
    :func:`groundlens.calibrate` on your own labelled data if you need a cut, and
    read the false-positive rate it hands back before you deploy it.
    """

    score: float
    k: int
    weakest: tuple[Anchor, ...]
    """The k anchors that produced ``score``, weakest first."""

    anchors: tuple[Anchor, ...]
    """Every word of the answer, in answer order, including skipped ones."""

    n_scored: int
    n_numeral: int
    encoder_id: str
    profile_sha256: str
    warnings: tuple[str, ...] = ()

    def report(self, limit: int | None = None) -> str:
        """The k weakest anchors as receipt lines."""
        rows = self.weakest if limit is None else self.weakest[:limit]
        return "\n".join(a.receipt() for a in rows)


@dataclass(frozen=True, slots=True)
class OperatingPoint:
    """A threshold measured on the user's own labelled data, with its cost attached."""

    threshold: float
    target_recall: float
    achieved_recall: float
    fpr: float
    """False-positive rate at this threshold. Read this before deploying."""

    fpr_ci95: tuple[float, float]
    n: int
    n_positive: int


@dataclass(frozen=True, slots=True)
class Evidence:
    """One retrieved source, with an id so findings can point at it."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class WindowEncoding:
    """What an :class:`Encoder` returns for one window of text.

    ``vectors`` must be L2-normalised so support is a plain dot product, and must
    have one row per entry in ``token_spans``.
    """

    token_spans: tuple[Span, ...]
    """Character offsets of each token, relative to the window's own text."""

    word_ids: tuple[int | None, ...]
    """Which pre-tokenised word each token belongs to. ``None`` for special tokens."""

    vectors: Sequence[Sequence[float]]
    """(n_tokens, dim), L2-normalised."""


@runtime_checkable
class Encoder(Protocol):
    """The one thing groundlens needs from a model.

    Implement this to use your own retrieval encoder. The reference
    implementation is :class:`groundlens.SentenceTransformerEncoder`, behind the
    ``[encoder]`` extra.
    """

    @property
    def id(self) -> str:
        """Stable identity including the exact revision, e.g.
        ``"all-mpnet-base-v2@bd44305fd6a1b43c16baf96765e2ecb20bca8e1d"``.

        A bare model name is not enough: a silent re-upload would change every
        number you ever published. This string goes into ``profile_sha256``.
        """

    @property
    def max_tokens(self) -> int:
        """Hard token limit per window, excluding special tokens."""

    def encode_window(self, text: str) -> WindowEncoding:
        """Embed one window. Text is guaranteed to fit within ``max_tokens``."""
