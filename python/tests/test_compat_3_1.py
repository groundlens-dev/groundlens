# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The numeral channel of proofread() must match groundlens 3.1 exactly.

The golden file was produced by 3.1 itself (see compat/generate_golden.py).
Numerals are exact arithmetic, so the tolerance here is zero: text, span,
support, canonical value, evidence id, evidence text, evidence span, notes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundlens import proofread

GOLDEN = json.loads((Path(__file__).parent / "compat" / "golden_numerals_3_1.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", GOLDEN["cases"], ids=[c["case"]["answer"][:30] for c in GOLDEN["cases"]])
def test_numeral_anchors_match_3_1(entry):
    case = entry["case"]
    marks = proofread(
        case["answer"],
        [tuple(x) for x in case["context"]],
        locale=case["locale"],
        question=case["question"],
    )
    got = [
        {
            "text": a.text,
            "span": list(a.span),
            "support": a.support,
            "value": a.value,
            "evidence_id": a.evidence_id,
            "evidence_text": a.evidence_text,
            "evidence_span": list(a.evidence_span) if a.evidence_span else None,
            "notes": list(a.notes),
        }
        for a in marks.anchors
        if a.kind == "numeral"
    ]
    assert got == entry["numerals"]


def test_floor_and_k_follow_3_1_rules():
    marks = proofread("Total 1,000 and 30 days", [("s", "total 10,000 in 30 days")])
    assert marks.k == 1
    assert marks.floor == 0.0
    assert marks.weakest[0].text == "1,000"
    empty = proofread("Nothing numeric.", [("s", "nothing")])
    assert empty.floor == 1.0 and empty.k == 0 and empty.n_marked == 0


def test_python_encoders_are_refused():
    with pytest.raises(TypeError):
        proofread("x 12", ["12"], encoder=object())
