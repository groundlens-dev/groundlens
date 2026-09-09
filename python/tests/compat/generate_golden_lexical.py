#!/usr/bin/env python3
"""Produce the 3.1 compatibility golden for the lexical channel.

Run with groundlens **3.1** on the path (tag v3.1.0), never with 4.0:

    pip install onnxruntime tokenizers numpy
    PYTHONPATH=/path/to/groundlens-3.1/src python generate_golden_lexical.py > golden_lexical_3_1.json

The encoder is the tiny test model of the engine (crates/gl-onnx/testdata/
tiny-bundle) run through onnxruntime and the HF tokenizers library, wrapped
in the 3.1 ``Encoder`` protocol. The engine runs the same graph through
tract. Every anchor 3.1 produces is recorded; the test compares text, span,
kind, evidence and notes exactly and support within the 1e-6 tolerance the
reproducible class declares.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from groundlens import proofread
from groundlens._types import WindowEncoding

BUNDLE = Path(__file__).resolve().parents[3] / "crates" / "gl-onnx" / "testdata" / "tiny-bundle"

CASES = [
    {"locale": "en", "question": "What is the invoice total?",
     "answer": "The invoice total is 1,000 dollars, due in 30 days.",
     "context": [("invoice.pdf#p1", "...the total amount due is 10,000 dollars, payable within 30 days...")]},
    {"locale": "es", "question": "¿Cuál es el importe de la factura?",
     "answer": "La factura asciende a 10.000 euros, pagaderos en 30 días en Madrid.",
     "context": [("factura", "Importe total: 10.000 euros, pagaderos en 30 días. Oficina registrada en Madrid.")]},
    {"locale": "de", "question": None,
     "answer": "Die Rechnung beläuft sich auf 1.000 Euro, zahlbar innerhalb von 30 Tagen.",
     "context": [("rechnung", "Die Rechnung beläuft sich auf 10.000 Euro, zahlbar innerhalb von 30 Tagen.")]},
    {"locale": "fr", "question": None,
     "answer": "Le contrat court sur 24 mois avec un taux de 3,90 % à Paris.",
     "context": [("contrat", "Le contrat court sur 24 mois avec un taux de 3,90 %."),
                 ("annexe", "Siège social à Paris.")]},
    {"locale": "it", "question": None,
     "answer": "I ricavi sono saliti a 37,35 miliardi di euro nel 2024 secondo il bilancio.",
     "context": [("bilancio", "I ricavi sono saliti a 37,35 miliardi di euro nel 2024.")]},
    {"locale": "en", "question": None,
     "answer": "The line is 1.2 km long and the boiling point is 212 °F, said the engineer from Lisbon.",
     "context": [("s", "Line length: 1200 m. Boiling point 100 °C. Engineer based in Porto.")]},
    {"locale": "en", "question": None,
     "answer": "Payment is due on 15 March 2025 at the registered office in Madrid, and the margin was four percent, which the auditor confirmed after reviewing the ledger twice.",
     "context": [("long", "Payment is due on 15 March 2025 at the registered office in Madrid. The auditor confirmed the margin after reviewing the ledger.")]},
    {"locale": "und", "question": None,
     "answer": "Nothing numeric here at all.",
     "context": [("n", "Still nothing.")]},
    {"locale": "und", "question": None,
     "answer": "Total 10,000 dollars.",
     "context": []},
]


class OnnxEncoder:
    """The 3.1 Encoder protocol over onnxruntime, mirroring gl-onnx exactly."""

    def __init__(self, root: Path) -> None:
        manifest = json.loads((root / "manifest.json").read_text())
        spec = manifest["encoders"]["default"]
        model_hash = manifest["artefacts"][spec["model"]]["sha256"]
        self._tok = Tokenizer.from_file(str(root / spec["tokenizer"]))
        self._sess = ort.InferenceSession(str(root / spec["model"]), providers=["CPUExecutionProvider"])
        self._max_tokens = spec["max_tokens"]
        self._prefix = spec.get("prefix", "")
        self.id = f"{Path(spec['model']).stem}@{model_hash}"

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def _content(self, text: str, offsets):
        """Byte offsets → char offsets, prefix and specials dropped (as gl-onnx)."""
        p = len(self._prefix.encode("utf-8"))
        full = (self._prefix + text).encode("utf-8")
        out = []
        for i, (a, b) in enumerate(offsets):
            if b <= a or a < p:
                continue
            ca = len(full[p:a].decode("utf-8"))
            cb = len(full[p:b].decode("utf-8"))
            out.append((i, (ca, cb)))
        return out

    def token_spans(self, text: str):
        enc = self._tok.encode(self._prefix + text, add_special_tokens=False)
        offsets = _byte_offsets(self._prefix + text, enc.offsets)
        return tuple(s for _, s in self._content(text, offsets))

    def encode_window(self, text: str) -> WindowEncoding:
        enc = self._tok.encode(self._prefix + text, add_special_tokens=True)
        offsets = _byte_offsets(self._prefix + text, enc.offsets)
        hidden = self._sess.run(
            None,
            {"input_ids": np.array([enc.ids], dtype=np.int64), "attention_mask": np.array([enc.attention_mask], dtype=np.int64)},
        )[0][0]
        keep = self._content(text, offsets)
        spans = tuple(s for _, s in keep)
        matrix = hidden[[i for i, _ in keep]].astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        vectors = (matrix / np.maximum(norms, 1e-12)).tolist() if len(keep) else []
        return WindowEncoding(token_spans=spans, word_ids=tuple(None for _ in spans), vectors=vectors)


def _byte_offsets(text: str, char_offsets):
    """The Python tokenizers binding reports char offsets; the Rust crate
    reports bytes. Work in bytes so the two implementations agree."""
    prefix = [0]
    for ch in text:
        prefix.append(prefix[-1] + len(ch.encode("utf-8")))
    return [(prefix[a], prefix[b]) for a, b in char_offsets]


def main() -> None:
    encoder = OnnxEncoder(BUNDLE)
    out = {"groundlens_version": "3.1.0", "encoder_id": encoder.id, "cases": []}
    for case in CASES:
        marks = proofread(case["answer"], case["context"], encoder=encoder, locale=case["locale"], question=case["question"])
        out["cases"].append(
            {
                "case": case,
                "floor": marks.floor,
                "k": marks.k,
                "n_marked": marks.n_marked,
                "anchors": [
                    {
                        "text": a.text,
                        "span": list(a.span),
                        "kind": a.kind,
                        "support": a.support,
                        "value": a.value,
                        "evidence_id": a.evidence_id,
                        "evidence_text": a.evidence_text,
                        "evidence_span": list(a.evidence_span) if a.evidence_span else None,
                        "notes": list(a.notes),
                    }
                    for a in marks.anchors
                ],
            }
        )
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
