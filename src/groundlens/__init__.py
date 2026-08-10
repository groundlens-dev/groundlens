"""groundlens -- which words in an answer your sources don't support, and what each lost to.

    >>> from groundlens import score, SentenceTransformerEncoder
    >>> profile = score(answer, [("policy.pdf#p3", passage)], encoder=SentenceTransformerEncoder())
    >>> print(profile.report())
    4.75%   support 0.00    nearest in policy.pdf#p3: '3.90%'

Two channels, two guarantees. **Numerals are decided by arithmetic**: support is
exactly 1.0 or exactly 0.0, from a Decimal comparison after formatting is
normalised, and it reproduces byte for byte on any machine. **Words are decided
by geometry**: a float32 cosine from a pinned encoder revision, reproducible to
1e-6 across platforms with stable ordering, but not bit-identical between x86
and Apple Silicon. We do not claim otherwise.

There is no verdict and no default threshold. See :class:`AnchorProfile` and
:func:`calibrate`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from groundlens._types import (
    NOTE_CODES,
    Anchor,
    AnchorKind,
    AnchorProfile,
    Encoder,
    Evidence,
    OperatingPoint,
    Span,
    WindowEncoding,
)
from groundlens.calibrate import calibrate
from groundlens.score import adaptive_k, score

if TYPE_CHECKING:  # pragma: no cover
    from groundlens._encode import SentenceTransformerEncoder

__version__ = "3.0.0"


def __getattr__(name: str) -> Any:
    """Expose ``SentenceTransformerEncoder`` without importing torch at import time.

    ``import groundlens`` must stay free. Only constructing the reference encoder
    should cost you a deep learning stack.
    """
    if name == "SentenceTransformerEncoder":
        from groundlens._encode import SentenceTransformerEncoder

        return SentenceTransformerEncoder
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "NOTE_CODES",
    "Anchor",
    "AnchorKind",
    "AnchorProfile",
    "Encoder",
    "Evidence",
    "OperatingPoint",
    "SentenceTransformerEncoder",
    "Span",
    "WindowEncoding",
    "__version__",
    "adaptive_k",
    "calibrate",
    "score",
]
