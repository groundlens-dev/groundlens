"""``question=``: not a source, only a note.

The question never adds support. What it adds is a way to tell an echo from a
finding, and the one guarantee that matters is that without it nothing changes.
"""

from __future__ import annotations

from groundlens import Anchor, Proofread, proofread

ANSWER = "The invoice total is 1,000 dollars, due in 30 days, payable to Acme Logistics."
SOURCES = [
    (
        "invoice.pdf#p1",
        "Invoice from Acme Logistics. The total amount due is 10,000 dollars, payable within 30 days of receipt.",
    )
]
QUESTION = "What is the invoice total, and is 1,000 dollars due in 30 days?"


def _by_text(marks: Proofread) -> dict[str, Anchor]:
    return {a.text: a for a in marks.anchors}


def test_without_a_question_nothing_changes(encoder) -> None:
    before = proofread(ANSWER, SOURCES, encoder=encoder, k=4)
    after = proofread(ANSWER, SOURCES, encoder=encoder, k=4, question=None)
    blank = proofread(ANSWER, SOURCES, encoder=encoder, k=4, question="   ")
    assert before == after == blank
    assert before.sha256 == after.sha256 == blank.sha256


def test_question_never_adds_support(encoder) -> None:
    plain = proofread(ANSWER, SOURCES, encoder=encoder, k=4)
    asked = proofread(ANSWER, SOURCES, encoder=encoder, k=4, question=QUESTION)
    assert [a.support for a in plain.anchors] == [a.support for a in asked.anchors]
    assert plain.floor == asked.floor
    assert [a.text for a in plain.weakest] == [a.text for a in asked.weakest]
    # the note is the only difference, so the hash must move -- it records the finding
    assert plain.sha256 != asked.sha256


def test_echoed_words_and_values_are_noted(encoder) -> None:
    marks = proofread(ANSWER, SOURCES, encoder=encoder, k=4, question=QUESTION)
    a = _by_text(marks)
    assert "echoes_question" in a["invoice"].notes
    assert "echoes_question" in a["total"].notes
    assert "echoes_question" in a["1,000"].notes  # the value 1000 is in the question
    assert "echoes_question" in a["30"].notes
    assert "echoes_question" not in a["Acme"].notes
    assert "echoes_question" not in a["payable"].notes


def test_the_unconfirmed_number_keeps_its_zero_and_says_so(encoder) -> None:
    """The case the note exists for: the model repeated the user, the source disagrees."""
    marks = proofread(ANSWER, SOURCES, encoder=encoder, k=1, question=QUESTION)
    a = _by_text(marks)["1,000"]
    assert a.kind == "numeral" and a.support == 0.0
    assert a.evidence_text == "10,000"
    assert "echoes_question" in a.notes
    assert "[also in the question]" in a.receipt()


def test_numeral_echo_matches_on_value_not_spelling(encoder) -> None:
    marks = proofread(ANSWER, SOURCES, encoder=encoder, k=1, question="Is it 1000 dollars?")
    assert "echoes_question" in _by_text(marks)["1,000"].notes


def test_word_echo_is_case_insensitive(encoder) -> None:
    marks = proofread(ANSWER, SOURCES, encoder=encoder, k=1, question="INVOICE?")
    assert "echoes_question" in _by_text(marks)["invoice"].notes


def test_note_code_is_registered() -> None:
    from groundlens import NOTE_CODES

    assert "echoes_question" in NOTE_CODES
