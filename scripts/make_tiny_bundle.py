"""Build the tiny test bundle under crates/gl-onnx/testdata/tiny-bundle.

A 16-dimensional contextual encoder with random (seeded) weights and a
WordPiece tokenizer trained on a few sentences in five languages. It knows
nothing about language; it exists so the lexical channel (windowing,
alignment, receipts, hashing) is tested end to end without the real model,
and so the golden file produced by groundlens 3.1 through onnxruntime can
be compared with the Rust engine through tract.

    pip install onnx tokenizers numpy
    python scripts/make_tiny_bundle.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, processors, trainers

ROOT = Path(__file__).resolve().parents[1] / "crates" / "gl-onnx" / "testdata" / "tiny-bundle"
DIM = 16
VOCAB = 512

CORPUS = [
    "The invoice total is 10,000 dollars, payable within 30 days.",
    "Revenue grew to 37.35 billion dollars in 2024 and the margin was 4.75%.",
    "La factura asciende a 10.000 euros, pagaderos en 30 días.",
    "Los ingresos crecieron hasta 37,35 mil millones de euros en 2024.",
    "Die Rechnung beläuft sich auf 10.000 Euro, zahlbar innerhalb von 30 Tagen.",
    "Der Umsatz stieg 2024 auf 37,35 Milliarden Euro.",
    "La facture s'élève à 10 000 euros, payable sous 30 jours.",
    "Le chiffre d'affaires a atteint 37,35 milliards d'euros en 2024.",
    "La fattura ammonta a 10.000 euro, pagabili entro 30 giorni.",
    "I ricavi sono saliti a 37,35 miliardi di euro nel 2024.",
    "The line is 1.2 km long and the boiling point is 212 °F.",
    "Payment is due on 15 March 2025 at the registered office in Madrid.",
    "El contrato tiene una duración de 24 meses y un interés del 3,90 %.",
    "Le contrat court sur 24 mois avec un taux de 3,90 %.",
    "Il contratto dura 24 mesi con un tasso del 3,90 %.",
    "Der Vertrag läuft 24 Monate mit einem Zinssatz von 3,90 %.",
]


def build_tokenizer(path: Path) -> None:
    tok = Tokenizer(models.WordPiece(unk_token="[UNK]"))
    tok.normalizer = normalizers.Sequence([normalizers.NFKC(), normalizers.Lowercase()])
    tok.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    trainer = trainers.WordPieceTrainer(
        vocab_size=VOCAB, special_tokens=["[PAD]", "[UNK]", "[CLS]", "[SEP]"], min_frequency=1
    )
    tok.train_from_iterator(CORPUS, trainer=trainer)
    tok.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]",
        special_tokens=[("[CLS]", tok.token_to_id("[CLS]")), ("[SEP]", tok.token_to_id("[SEP]"))],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tok.save(str(path))


def build_model(path: Path) -> None:
    rng = np.random.default_rng(20260908)
    table = rng.normal(0, 1, (VOCAB, DIM)).astype(np.float32)
    mix = rng.normal(0, 0.3, (DIM, DIM)).astype(np.float32)

    ids = helper.make_tensor_value_info("input_ids", TensorProto.INT64, [1, "S"])
    mask = helper.make_tensor_value_info("attention_mask", TensorProto.INT64, [1, "S"])
    out = helper.make_tensor_value_info("last_hidden_state", TensorProto.FLOAT, [1, "S", DIM])

    nodes = [
        helper.make_node("Gather", ["table", "input_ids"], ["emb"], axis=0),  # [1,S,D]
        helper.make_node("Cast", ["attention_mask"], ["maskf"], to=TensorProto.FLOAT),  # [1,S]
        helper.make_node("Unsqueeze", ["maskf", "axes2"], ["mask3"]),  # [1,S,1]
        helper.make_node("Mul", ["emb", "mask3"], ["masked"]),
        helper.make_node("ReduceSum", ["masked", "axes1"], ["sum"], keepdims=1),  # [1,1,D]
        helper.make_node("ReduceSum", ["mask3", "axes1"], ["count"], keepdims=1),  # [1,1,1]
        helper.make_node("Div", ["sum", "count"], ["mean"]),
        helper.make_node("MatMul", ["mean", "mix"], ["ctx"]),  # [1,1,D]
        helper.make_node("Add", ["emb", "ctx"], ["pre"]),
        helper.make_node("Tanh", ["pre"], ["last_hidden_state"]),
    ]
    graph = helper.make_graph(
        nodes,
        "tiny-contextual-encoder",
        [ids, mask],
        [out],
        initializer=[
            numpy_helper.from_array(table, "table"),
            numpy_helper.from_array(mix, "mix"),
            numpy_helper.from_array(np.array([1], dtype=np.int64), "axes1"),
            numpy_helper.from_array(np.array([2], dtype=np.int64), "axes2"),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], producer_name="groundlens-tiny")
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
    artefacts = {}
    for p, kind in [(model, "onnx-model"), (tokenizer, "tokenizer")]:
        rel = p.relative_to(ROOT).as_posix()
        artefacts[rel] = {
            "path": rel,
            "sha256": sha256(p),
            "bytes": p.stat().st_size,
            "kind": kind,
            "used_by": ["groundlens.lexical"],
        }
    manifest = {
        "schema": "groundlens.bundle-manifest/1",
        "name": "tiny-test",
        "version": "1",
        "engine_version": "4.0.0",
        "execution_profile": "cpu-f32",
        "artefacts": artefacts,
        "offline_only": True,
        "encoders": {
            "default": {
                "model": "models/tiny.onnx",
                "tokenizer": "tokenizers/tiny/tokenizer.json",
                "max_tokens": 24,
                "prefix": "",
                "pooling": "mean",
                "dim": DIM,
            }
        },
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("wrote", ROOT)


if __name__ == "__main__":
    main()
