#!/usr/bin/env python3
"""Emit the canonical structural output of the deterministic path, as JSON.

CI runs this on every (OS, Python) cell in the matrix and byte-diffs the
results against each other and against a committed golden file. If any cell
disagrees by a single byte, the build goes red.

This is deliberately the *structural* path only -- segmentation, numeral
readings, spans, notes. All of it is exact and all of it must be identical
everywhere. The lexical channel is float32 cosine and is checked separately,
to a tolerance, because claiming bit-identical floats across x86 and Apple
Silicon would be a claim we cannot keep.

Usage:  python scripts/dump_fixture.py > fixture.json
"""

from __future__ import annotations

import json
import sys

from groundlens._numerals import format_decimal, locale
from groundlens._text import normalised
from groundlens._words import segment

#: Every line here exists because it broke something. Add, never remove.
CORPUS: tuple[tuple[str, str], ...] = (
    ("und", "According to the invoice, the total amount due is 10,000 dollars."),
    ("und", "The invoice states a total of 1,000 dollars due within 30 days."),
    ("und", "10000 and 10,000 and $10,000 and 10 000 and 10 000"),
    ("und", "1.234 is ambiguous; 1.234.567 is not; 1.000,50 is one thousand."),
    ("es", "El importe total asciende a 1.250,50 EUR con vencimiento en 30 dias."),
    ("en", "Revenue of (1,500) against a forecast of 3.5% and 1'000 units."),
    ("de", "Der Betrag betragt 1.000,50 EUR."),
    ("und", "Step 1 then step 2 then step 10 of 12."),
    ("und", "10，000 full-width and 10\u200b,\u200b000 invisible."),
    ("und", "non-binding client's offer, not a recommendation"),
    ("und", "-1,500 and −1,500 and +1,500"),
    ("und", "請求書の合計金額は10,000ドルです。"),
)


def dump() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for locale_name, raw in CORPUS:
        profile = locale(locale_name)
        text = normalised(raw)
        rows.append(
            {
                "locale": locale_name,
                "text": text,
                "units": [
                    {
                        "text": unit.text,
                        "span": list(unit.span),
                        "kind": unit.kind,
                        "notes": list(unit.notes),
                        "readings": (
                            [format_decimal(r) for r in unit.numeral.readings]
                            if unit.numeral is not None
                            else None
                        ),
                    }
                    for unit in segment(text, profile)
                ],
            }
        )
    return rows


def main() -> None:
    # sort_keys and a fixed separator set: the output is a hash input, not a view.
    json.dump(dump(), sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
