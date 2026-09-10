# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The lexical channel of proofread() must match groundlens 3.1.

The golden file was produced by 3.1 itself over the tiny test encoder run
through onnxruntime (see compat/generate_golden_lexical.py). The engine runs
the same ONNX graph through tract. Anchors must agree on text, span, kind,
evidence id, evidence text, evidence span and notes; support agrees within
the 1e-6 tolerance of the reproducible class (the engine quantises scores
to six decimals, 3.1 did not).

One deliberate difference: 4.0 skips the function words of the document's
locale (es, ca, gl, de, fr, it), where 3.x skipped only English ones. A
golden lexical anchor the engine now reports as ``skipped`` is accepted
when, and only when, it is a stopword of that locale.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundlens import _engine, proofread

HERE = Path(__file__).parent
GOLDEN = json.loads((HERE / "compat" / "golden_lexical_3_1.json").read_text(encoding="utf-8"))
TINY = HERE.parents[1] / "crates" / "gl-onnx" / "testdata" / "tiny-bundle"
TOLERANCE = 1e-6


def _stopword(text: str, locale: str) -> bool:
    words = json.loads(_engine.segment_json(text, locale))
    return bool(words) and words[0]["stopword"]


@pytest.mark.parametrize("entry", GOLDEN["cases"], ids=[c["case"]["answer"][:30] for c in GOLDEN["cases"]])
def test_lexical_anchors_match_3_1(entry):
    case = entry["case"]
    marks = proofread(
        case["answer"],
        [tuple(x) for x in case["context"]],
        locale=case["locale"],
        question=case["question"],
        bundle=TINY,
    )
    assert marks.encoder_id == GOLDEN["encoder_id"]
    ours = {tuple(a.span): a for a in marks.anchors}
    reclassified = 0
    for g in entry["anchors"]:
        a = ours[tuple(g["span"])]
        assert a.text == g["text"]
        if g["kind"] == "lexical" and a.kind == "skipped":
            assert _stopword(g["text"], case["locale"]), f"{g['text']!r} skipped but not a stopword"
            reclassified += 1
            continue
        assert a.kind == g["kind"]
        assert a.evidence_id == g["evidence_id"]
        assert a.evidence_text == g["evidence_text"]
        assert (list(a.evidence_span) if a.evidence_span else None) == g["evidence_span"]
        assert sorted(a.notes) == sorted(g["notes"]), (a.text, a.notes, g["notes"])
        assert abs(a.support - g["support"]) <= TOLERANCE, (a.text, a.support, g["support"])
    assert len(marks.anchors) == len(entry["anchors"])
    if reclassified == 0:
        assert marks.k == entry["k"]
        assert marks.n_marked == entry["n_marked"]
        assert abs(marks.floor - entry["floor"]) <= TOLERANCE


def test_without_a_bundle_words_are_reported_not_scored():
    marks = proofread("Total 1,000 dollars", [("s", "Total 10,000 dollars")], bundle=None)
    if marks.encoder_id != "none":
        pytest.skip("a base bundle is installed on this machine")
    words = [a for a in marks.anchors if a.kind == "lexical"]
    assert words and all("not_scored" in a.notes for a in words)
    assert any("bundle pull base" in w for w in marks.warnings)
    assert marks.n_marked == 1  # the numeral


def test_python_encoders_are_refused_with_guidance():
    with pytest.raises(TypeError, match="bundle"):
        proofread("x 12", ["12"], encoder=object())
