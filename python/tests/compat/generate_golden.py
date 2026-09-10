#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Produce the 3.1 compatibility golden for the numeral channel.

Run with groundlens **3.1** on the path (the archived tag), never with 4.0:

    PYTHONPATH=/path/to/groundlens-3.1/src python generate_golden.py > golden_numerals_3_1.json

A dummy encoder is used so the lexical channel runs without a model; only
numeral anchors are recorded, and they do not depend on the encoder.
"""

from __future__ import annotations

import json
import sys

from groundlens import proofread
from groundlens._types import WindowEncoding

CASES = [
    {"locale": "und", "question": "What is the invoice total?",
     "answer": "The invoice total is 1,000 dollars, due in 30 days.",
     "context": [("invoice.pdf#p1", "...the total amount due is 10,000 dollars, payable within 30 days...")]},
    {"locale": "en", "question": "Is the rate 4.75%, and what is the payment term?",
     "answer": "The invoice total is 4.75% payable within 45 days.",
     "context": [("policy.pdf#p3", "The rate stated in the policy is 3.90% and the term is 30 days.")]},
    {"locale": "und", "question": None,
     "answer": "1.234 is ambiguous and 1.234.567 is not and 1.000,50 is one thousand.",
     "context": [("a", "Values: 1234 and 1234567 and 1000.5")]},
    {"locale": "es", "question": None,
     "answer": "El importe total asciende a 1.250,50 EUR con vencimiento en 30 dias.",
     "context": [("factura", "Importe: 1250,50 euros. Plazo: 30 dias.")]},
    {"locale": "en", "question": None,
     "answer": "Revenue of (1,500) against a forecast of 3.5% and 1'000 units.",
     "context": [("q", "forecast 3.5 percent; units 1000; revenue -1500")]},
    {"locale": "de", "question": None,
     "answer": "Der Betrag betragt 1.000,50 EUR.",
     "context": [("de", "Betrag 1000,50")]},
    {"locale": "und", "question": None,
     "answer": "Step 1 then step 2 then step 10 of 12.",
     "context": [("s", "There are 12 steps; step 10 is last.")]},
    {"locale": "und", "question": None,
     "answer": "-1,500 and −1,500 and +1,500 and payment - $101,755",
     "context": [("p", "loss of 1,500; payment of $101,755")]},
    {"locale": "und", "question": "How much is the fee, 250?",
     "answer": "The fee is 250 and the cap is 10,000.",
     "context": [("f", "cap: 10000")]},
    {"locale": "und", "question": None,
     "answer": "Nothing numeric here at all.",
     "context": [("n", "Still nothing.")]},
    {"locale": "und", "question": None,
     "answer": "Total 10,000 dollars.",
     "context": []},
    {"locale": "en", "question": None,
     "answer": "Docling writes $ 5,428 and 3,14 for tables.",
     "context": [("t", "amount $5,428 and ratio 3.14")]},
]


class DummyEncoder:
    """Whitespace tokens, zero vectors. Numeral anchors never touch it."""

    id = "dummy@0"
    max_tokens = 512

    def token_spans(self, text):
        spans, i = [], 0
        for tok in text.split(" "):
            if tok:
                spans.append((i, i + len(tok)))
            i += len(tok) + 1
        return tuple(spans)

    def encode_window(self, text):
        spans = self.token_spans(text)
        return WindowEncoding(token_spans=spans, word_ids=tuple(range(len(spans))), vectors=[[0.0, 0.0] for _ in spans])


def main() -> None:
    out = []
    for case in CASES:
        marks = proofread(case["answer"], case["context"], encoder=DummyEncoder(), locale=case["locale"], question=case["question"])
        out.append({
            "case": case,
            "numerals": [
                {"text": a.text, "span": list(a.span), "support": a.support, "value": a.value,
                 "evidence_id": a.evidence_id, "evidence_text": a.evidence_text,
                 "evidence_span": list(a.evidence_span) if a.evidence_span else None, "notes": list(a.notes)}
                for a in marks.anchors if a.kind == "numeral"
            ],
        })
    json.dump({"source": "groundlens 3.1.0", "cases": out}, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
