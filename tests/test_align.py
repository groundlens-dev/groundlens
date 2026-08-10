"""Windowing invariants.

These tests exist because of a specific bug in the code this library replaces:
a hard token cap silently dropped words past the limit, and because the floor
is a floor, dropping words could only push it up. Long answers then read as
better grounded than they were. Every assertion here is aimed at that.
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from conftest import FakeEncoder

from groundlens._align import STRIDE_RATIO, embed, plan_windows, tokens_overlapping
from groundlens._numerals import locale
from groundlens._words import segment
from groundlens.proofread import proofread

UND = locale("und")


def test_short_text_is_one_window() -> None:
    encoder = FakeEncoder(max_tokens=64)
    assert len(plan_windows("the total is 10,000 dollars", encoder)) == 1


def test_long_text_is_covered_completely() -> None:
    """Every token must appear in at least one window. This is the bug."""
    encoder = FakeEncoder(max_tokens=8)
    text = " ".join(f"word{i}" for i in range(200))
    windows = plan_windows(text, encoder)
    covered: set[int] = set()
    for window in windows:
        covered.update(range(window.first_token, window.last_token + 1))
    assert covered == set(range(len(encoder.token_spans(text))))


def test_windows_never_exceed_the_encoder_limit() -> None:
    """FakeEncoder.encode_window raises above max_tokens, so this is enforced twice."""
    encoder = FakeEncoder(max_tokens=8)
    text = " ".join(f"word{i}" for i in range(200))
    for window in plan_windows(text, encoder):
        assert len(encoder.token_spans(window.text)) <= encoder.max_tokens
        encoder.encode_window(window.text)


def test_windows_overlap_by_the_stride() -> None:
    encoder = FakeEncoder(max_tokens=10)
    text = " ".join(f"word{i}" for i in range(100))
    windows = plan_windows(text, encoder)
    assert len(windows) > 1
    stride = max(1, int(encoder.max_tokens * STRIDE_RATIO))
    for previous, following in pairwise(windows):
        assert following.first_token - previous.first_token == stride


def test_embedding_covers_every_character_of_a_long_answer() -> None:
    encoder = FakeEncoder(max_tokens=8)
    text = " ".join(f"word{i}" for i in range(300))
    tokens = embed(text, encoder)
    for unit in segment(text, UND):
        assert tokens_overlapping(unit.span, tokens), f"{unit.text} aligned to nothing"


@pytest.mark.parametrize("max_tokens", [4, 8, 16, 64, 4096])
def test_no_scoring_word_is_ever_dropped(max_tokens: int) -> None:
    """The invariant, stated once: anchors out == scoring units in.

    Run across window sizes from absurdly small to larger than the text, because
    the failure only appears when the cap actually bites.
    """
    encoder = FakeEncoder(max_tokens=max_tokens)
    answer = " ".join(f"alpha{i} 1{i:03d}" for i in range(120))
    context = answer
    profile = proofread(answer, context, encoder=encoder, k=1)
    expected = len([u for u in segment(answer, UND) if u.kind != "skipped"])
    assert profile.n_marked == expected


def test_a_long_answer_does_not_floor_higher_than_the_same_answer_short() -> None:
    """The exact shape of the old bug: truncation inflates a floor.

    A wrong number buried 400 words into an answer must land the same as the
    same wrong number in the first sentence.
    """
    encoder = FakeEncoder(max_tokens=8)
    context = "the total amount due is 10,000 dollars"
    filler = " ".join(["the total amount due"] * 100)
    early = proofread("total 1,000 due " + filler, context, encoder=encoder, k=1)
    late = proofread(filler + " total 1,000 due", context, encoder=encoder, k=1)
    assert early.floor == late.floor == 0.0
    assert early.weakest[0].text == late.weakest[0].text == "1,000"


def test_word_on_a_window_boundary_still_finds_its_anchor() -> None:
    encoder = FakeEncoder(max_tokens=6)
    context = "the settlement amount is 12,500 euros payable immediately"
    answer = " ".join(["padding"] * 20) + " settlement 12,500 euros"
    profile = proofread(answer, context, encoder=encoder, k=1)
    numerals = [a for a in profile.anchors if a.kind == "numeral"]
    assert [a.support for a in numerals] == [1.0]


def test_empty_context_is_a_warning_not_a_crash() -> None:
    encoder = FakeEncoder()
    profile = proofread("the total is 10,000 dollars", "", encoder=encoder, k=1)
    assert profile.warnings
    assert "no context" in profile.warnings[0]
