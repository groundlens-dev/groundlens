"""groundlens -- which words in an answer your sources don't support, and what each lost to.

    >>> from groundlens import score, SentenceTransformerEncoder
    >>> profile = score(answer, [("policy.pdf#p3", passage)], encoder=SentenceTransformerEncoder())
    >>> print(profile.report())
    4.75%   support 0.00    nearest in policy.pdf#p3: '3.90%'

Two channels, two guarantees. Numerals are decided by arithmetic: a numeral's
support is exactly 1.0 or exactly 0.0, from a Decimal comparison, and reproduces
byte for byte on any machine. Words are decided by geometry: a float32 cosine
from a pinned encoder revision, reproducible to 1e-6 across platforms with a
stable ordering, but not bit-identical between x86 and Apple Silicon. We do not
claim otherwise.

There is no verdict and no default threshold. See :class:`AnchorProfile`.
"""

from __future__ import annotations

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

__version__ = "3.0.0"

__all__ = [
    "NOTE_CODES",
    "Anchor",
    "AnchorKind",
    "AnchorProfile",
    "Encoder",
    "Evidence",
    "OperatingPoint",
    "Span",
    "WindowEncoding",
    "__version__",
]
