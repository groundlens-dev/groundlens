"""Input normalisation. Applied exactly once, before anything else looks at the text.

Every character span in a result -- ``Anchor.span``, ``Anchor.evidence_span`` --
is an offset into the *normalised* string, never the caller's original. That is
the only way spans can be stable, because normalisation changes lengths.
:func:`normalised` is idempotent, and a test asserts it.
"""

from __future__ import annotations

import re
import unicodedata

#: Codepoints deleted outright. They carry no meaning for grounding and they
#: break span arithmetic and equality checks in ways that are painful to debug.
INVISIBLE = frozenset(
    {
        "­",  # soft hyphen
        "\u200b",  # zero-width space
        "‌",  # zero-width non-joiner
        "‍",  # zero-width joiner
        "⁠",  # word joiner
        "﻿",  # byte-order mark
    }
)

#: Space-like codepoints that must survive as *distinct* characters, because
#: they are digit group separators in real European documents (1 234,50).
#: They are normalised to a single canonical form, not collapsed to " ".
THIN_SPACES = {
    " ": " ",  # thin space -> narrow no-break space
    " ": " ",  # figure space
    " ": " ",  # no-break space
}

_NEWLINES = re.compile(r"\r\n?")
_HORIZONTAL_RUN = re.compile(r"[ \t\v\f]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalised(text: str) -> str:
    """NFKC-normalise, delete invisibles, canonicalise spaces and line endings.

    NFKC is chosen over NFC deliberately: it folds full-width digits, ligatures
    and superscripts onto their ASCII equivalents, so a numeral written １０，０００
    parses to the same value as 10,000.
    """
    text = _NEWLINES.sub("\n", text)
    text = unicodedata.normalize("NFKC", text)
    # NFKC maps U+00A0 to a plain space, so re-mark group separators only where
    # they still survive (some inputs use U+202F, which NFKC leaves alone).
    out = []
    for ch in text:
        if ch in INVISIBLE:
            continue
        out.append(THIN_SPACES.get(ch, ch))
    text = "".join(out)
    text = _HORIZONTAL_RUN.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def is_normalised(text: str) -> bool:
    return normalised(text) == text
