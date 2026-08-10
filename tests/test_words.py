from __future__ import annotations

from itertools import pairwise

from groundlens._numerals import locale
from groundlens._text import normalised
from groundlens._words import content_word_count, segment, segmentation_warnings

UND = locale("und")


def kinds(text: str) -> list[tuple[str, str]]:
    return [(u.text, u.kind) for u in segment(normalised(text), UND)]


def test_a_number_is_one_word_not_three() -> None:
    """A BERT pre-tokenizer splits 10,000 into `10` `,` `000`. That split is
    exactly where a wrong number hides, so the library segments its own words."""
    units = [u for u in segment("the total is 10,000 dollars", UND) if u.kind == "numeral"]
    assert [u.text for u in units] == ["10,000"]


def test_numerals_win_overlaps_but_do_not_swallow_the_next_word() -> None:
    assert kinds("payable within 30 days") == [
        ("payable", "lexical"),
        ("within", "skipped"),
        ("30", "numeral"),
        ("days", "lexical"),
    ]


def test_stopwords_are_skipped_not_dropped() -> None:
    units = segment("the invoice", UND)
    assert [(u.text, u.kind, u.notes) for u in units] == [
        ("the", "skipped", ("stopword",)),
        ("invoice", "lexical", ()),
    ]


def test_every_unit_has_a_span_that_round_trips() -> None:
    text = normalised("According to the invoice, the total is 10,000 dollars within 30 days.")
    for unit in segment(text, UND):
        start, end = unit.span
        assert text[start:end] == unit.text, (unit.text, text[start:end])


def test_units_are_in_answer_order_and_do_not_overlap() -> None:
    text = normalised("A total of 10,000 EUR and 1.250,50 EUR was invoiced in 2024.")
    units = segment(text, UND)
    spans = [u.span for u in units]
    assert spans == sorted(spans)
    for (_, prev_end), (next_start, _) in pairwise(spans):
        assert prev_end <= next_start


def test_hyphenated_and_apostrophed_words_stay_whole() -> None:
    assert kinds("non-binding client's offer") == [
        ("non-binding", "lexical"),
        ("client's", "lexical"),
        ("offer", "lexical"),
    ]


def test_content_word_count_is_stable_under_normalisation() -> None:
    raw = "The  total\r\nis 10,000\u200b dollars"
    assert content_word_count(normalised(raw), UND) == 3  # total, 10,000, dollars


def test_unsegmented_script_is_warned_about_not_silently_marked() -> None:
    assert segmentation_warnings("the total is 10,000 dollars") == ()
    warnings = segmentation_warnings(
        "請求書の合計金額は10,000ドルです。支払期限は納品後30日以内です。"
    )
    assert warnings and "unsegmented" in warnings[0]
