# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Build the tiny NLI test model under crates/gl-onnx/testdata/tiny-nli.

A 3-class sequence classifier with random (seeded) weights and a WordPiece
tokenizer that encodes a (premise, hypothesis) pair as
`[CLS] premise [SEP] hypothesis [SEP]`. It knows nothing about entailment; it
exists so the NLI runner (pair tokenisation, forward pass, softmax, label
mapping) and the NliVerifier are tested end to end without the real model.

    pip install onnx tokenizers numpy
    python scripts/make_tiny_nli.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, processors, trainers

ROOT = Path(__file__).resolve().parents[1] / "crates" / "gl-onnx" / "testdata" / "tiny-nli"
DIM = 16
VOCAB = 512
# Logit order, matching the MoritzLaurer mnli-xnli models we target.
LABELS = ["entailment", "neutral", "contradiction"]

CORPUS = [
    "The invoice total is 10,000 dollars.",
    "Revenue grew to 37.35 billion dollars in 2024.",
    "La factura asciende a 10.000 euros.",
    "Los ingresos crecieron hasta 37,35 mil millones en 2024.",
    "Die Rechnung beläuft sich auf 10.000 Euro.",
    "Le chiffre d'affaires a atteint 37,35 milliards d'euros.",
    "La fattura ammonta a 10.000 euro.",
    "The contract runs for 24 months at 3.90 percent.",
]


def build_tokenizer(path: Path) -> None:
    tok = Tokenizer(models.WordPiece(unk_token="[UNK]"))
    tok.normalizer = normalizers.Sequence([normalizers.NFKC(), normalizers.Lowercase()])
    tok.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    trainer = trainers.WordPieceTrainer(
        vocab_size=VOCAB, special_tokens=["[PAD]", "[UNK]", "[CLS]", "[SEP]"], min_frequency=1
    )
    tok.train_from_iterator(CORPUS, trainer=trainer)
    cls = tok.token_to_id("[CLS]")
    sep = tok.token_to_id("[SEP]")
    # A pair is encoded as [CLS] premise [SEP] hypothesis [SEP].
    tok.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]",
        pair="[CLS] $A [SEP] $B:1 [SEP]:1",
        special_tokens=[("[CLS]", cls), ("[SEP]", sep)],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tok.save(str(path))


def build_model(path: Path) -> None:
    rng = np.random.default_rng(20260919)
    table = rng.normal(0, 1, (VOCAB, DIM)).astype(np.float32)
    clsw = rng.normal(0, 0.5, (DIM, 3)).astype(np.float32)
    clsb = rng.normal(0, 0.1, (3,)).astype(np.float32)

    ids = helper.make_tensor_value_info("input_ids", TensorProto.INT64, [1, "S"])
    mask = helper.make_tensor_value_info("attention_mask", TensorProto.INT64, [1, "S"])
    out = helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 3])

    nodes = [
        helper.make_node("Gather", ["table", "input_ids"], ["emb"], axis=0),  # [1,S,D]
        helper.make_node("Cast", ["attention_mask"], ["maskf"], to=TensorProto.FLOAT),  # [1,S]
        helper.make_node("Unsqueeze", ["maskf", "axes2"], ["mask3"]),  # [1,S,1]
        helper.make_node("Mul", ["emb", "mask3"], ["masked"]),
        helper.make_node("ReduceSum", ["masked", "axes1"], ["sum"], keepdims=0),  # [1,D]
        helper.make_node("ReduceSum", ["mask3", "axes1"], ["count"], keepdims=0),  # [1,1]
        helper.make_node("Div", ["sum", "count"], ["pooled"]),  # [1,D]
        helper.make_node("MatMul", ["pooled", "clsw"], ["proj"]),  # [1,3]
        helper.make_node("Add", ["proj", "clsb"], ["logits"]),  # [1,3]
    ]
    graph = helper.make_graph(
        nodes,
        "tiny-nli-classifier",
        [ids, mask],
        [out],
        initializer=[
            numpy_helper.from_array(table, "table"),
            numpy_helper.from_array(clsw, "clsw"),
            numpy_helper.from_array(clsb, "clsb"),
            numpy_helper.from_array(np.array([1], dtype=np.int64), "axes1"),
            numpy_helper.from_array(np.array([2], dtype=np.int64), "axes2"),
        ],
    )
    model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 13)], producer_name="groundlens-tiny-nli"
    )
    model.ir_version = 8
    onnx.checker.check_model(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(path))


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    model = ROOT / "models" / "tiny.onnx"
    tokenizer = ROOT / "tokenizers" / "tiny" / "tokenizer.json"
    build_model(model)
    build_tokenizer(tokenizer)
    spec = {
        "model": "models/tiny.onnx",
        "tokenizer": "tokenizers/tiny/tokenizer.json",
        "max_tokens": 32,
        "labels": LABELS,
    }
    (ROOT / "spec.json").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    for p in (model, tokenizer):
        print(p.relative_to(ROOT).as_posix(), sha256(p), p.stat().st_size)
    print("wrote", ROOT)


if __name__ == "__main__":
    main()
