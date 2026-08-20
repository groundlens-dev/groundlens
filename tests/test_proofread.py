"""The metric, and the promises the README makes about it."""

from __future__ import annotations

import pytest
from conftest import (
    INVOICE_CONTEXT,
    INVOICE_GROUNDED,
    INVOICE_PERTURBED,
    INVOICE_REFORMATTED,
    FakeEncoder,
)

from groundlens import Evidence, Proofread, adaptive_k, proofread

BIG = FakeEncoder(max_tokens=512)


def run(answer: str, context: object = INVOICE_CONTEXT, **kwargs: object) -> Proofread:
    return proofread(answer, context, encoder=BIG, **kwargs)  # type: ignore[arg-type]


# --- ten is not a hundred -------------------------------------------------


def test_a_wrong_number_collapses_the_proofread() -> None:
    # approx on the upper end: lexical support is a float32 cosine and lands at
    # 0.99999994 for an exact string match. The numeral channel is exact.
    assert run(INVOICE_GROUNDED).floor == pytest.approx(1.0, abs=1e-6)
    assert run(INVOICE_PERTURBED).floor == 0.0


def test_a_reformatted_number_does_not() -> None:
    """10000 and 10,000 are the same number. Penalising the rewrite is a false alarm."""
    assert run(INVOICE_REFORMATTED).floor == run(INVOICE_GROUNDED).floor


def test_the_alarm_names_the_word_and_the_source_number() -> None:
    weakest = run(INVOICE_PERTURBED).weakest[0]
    assert weakest.text == "1,000"
    assert weakest.support == 0.0
    assert weakest.kind == "numeral"
    assert weakest.evidence_text == "10,000"
    assert weakest.evidence_id == "ctx-0"


def test_the_receipt_line_is_the_product() -> None:
    profile = proofread(
        "The invoice total is 4.75% payable within 45 days",
        [("policy.pdf#p3", "The rate stated in the policy is 3.90% and the term is 30 days")],
        encoder=BIG,
        k=2,
    )
    assert "4.75%" in profile.report()
    assert "3.90%" in profile.report()
    assert "policy.pdf#p3" in profile.report()


def test_the_source_word_is_a_real_slice_of_the_source() -> None:
    profile = run(INVOICE_PERTURBED)
    for anchor in profile.anchors:
        if anchor.evidence_span is None:
            continue
        start, end = anchor.evidence_span
        assert INVOICE_CONTEXT[start:end] == anchor.evidence_text


# --- floor, not mean ------------------------------------------------------


def test_the_floor_catches_what_the_mean_hides() -> None:
    """One wrong token in a long correct answer. The mean says fine, the floor alarms."""
    profile = run(INVOICE_PERTURBED)
    supports = [a.support for a in profile.anchors if a.kind != "skipped"]
    mean = sum(supports) / len(supports)
    assert mean > 0.85  # "looks fine"
    assert profile.floor == 0.0


def test_a_proven_wrong_number_outranks_an_unanchored_word() -> None:
    """Both sit at 0.0 and they are not the same kind of zero.

    Arithmetic proves the number is absent. A word at 0.0 only failed to find a
    lexical anchor, which is ordinary in honest paraphrase.
    """
    profile = proofread(
        "the 1,000 dollars zzzqqx",
        "the total amount due is 10,000 dollars",
        encoder=BIG,
        k=2,
    )
    assert profile.weakest[0].text == "1,000"
    assert profile.weakest[0].kind == "numeral"


@pytest.mark.parametrize(("n", "expected"), [(1, 1), (6, 1), (7, 2), (20, 3), (27, 4), (400, 4)])
def test_adaptive_k(n: int, expected: int) -> None:
    assert adaptive_k(n) == expected


def test_k_zero_selects_the_adaptive_rule() -> None:
    profile = run(INVOICE_GROUNDED, k=0)
    assert profile.k == adaptive_k(profile.n_marked)


def test_k_never_exceeds_the_number_of_anchors() -> None:
    assert run("10,000", k=9).k == 1


# --- there is no verdict --------------------------------------------------


def test_the_result_carries_no_decision() -> None:
    """If a verdict ever appears here, someone will deploy it. Nothing supports one."""
    profile = run(INVOICE_GROUNDED)
    for banned in ("decision", "verdict", "passed", "is_hallucination", "flag", "label"):
        assert not hasattr(profile, banned), f"Proofread grew a {banned!r} field"


def test_no_module_exports_a_default_threshold() -> None:
    import groundlens
    from groundlens import proofread as proofread_module

    for module in (groundlens, proofread_module):
        for name in dir(module):
            assert "THRESHOLD" not in name.upper()


# --- structure and reporting ----------------------------------------------


def test_every_word_appears_in_anchors_including_stopwords() -> None:
    profile = run(INVOICE_GROUNDED)
    assert [a.text for a in profile.anchors if a.kind == "skipped"]
    assert profile.n_marked == len([a for a in profile.anchors if a.kind != "skipped"])


def test_spans_round_trip_against_the_normalised_answer() -> None:
    from groundlens._text import normalised

    text = normalised(INVOICE_GROUNDED)
    for anchor in run(INVOICE_GROUNDED).anchors:
        start, end = anchor.span
        assert text[start:end] == anchor.text


def test_evidence_ids_are_preserved_across_input_shapes() -> None:
    passages = ["the total is 10,000 dollars", "payable within 30 days"]
    plain = run("the total 10,000 dollars", passages)
    tagged = run("the total 10,000 dollars", [("a.pdf", passages[0]), ("b.pdf", passages[1])])
    objects = run(
        "the total 10,000 dollars",
        [Evidence("a.pdf", passages[0]), Evidence("b.pdf", passages[1])],
    )
    assert {a.evidence_id for a in plain.anchors if a.evidence_id} <= {"ctx-0", "ctx-1"}
    assert tagged.floor == objects.floor == plain.floor
    assert {a.evidence_id for a in tagged.anchors if a.evidence_id} <= {"a.pdf", "b.pdf"}


def test_bad_context_type_is_refused_clearly() -> None:
    with pytest.raises(TypeError, match="context items must be"):
        run(INVOICE_GROUNDED, [42])


def test_absurdly_long_answers_are_refused_not_silently_slow() -> None:
    with pytest.raises(ValueError, match="max_anchors"):
        run(" ".join(f"word{i}" for i in range(50)), max_anchors=10)


# --- reproducibility ------------------------------------------------------


def test_the_hash_is_stable_and_discriminating() -> None:
    assert run(INVOICE_GROUNDED).sha256 == run(INVOICE_GROUNDED).sha256
    assert run(INVOICE_GROUNDED).sha256 != run(INVOICE_PERTURBED).sha256


def test_the_hash_covers_the_encoder_identity() -> None:
    """A silent re-upload of a checkpoint must not go unnoticed in a published hash."""
    a = proofread(INVOICE_GROUNDED, INVOICE_CONTEXT, encoder=BIG)

    class Relabelled(FakeEncoder):
        @property
        def id(self) -> str:
            return "fake-trigram-64@v2"

    b = proofread(INVOICE_GROUNDED, INVOICE_CONTEXT, encoder=Relabelled(max_tokens=512))
    assert a.floor == pytest.approx(b.floor)
    assert a.sha256 != b.sha256


def test_locale_changes_what_a_number_means() -> None:
    spanish = proofread(
        "el importe es 1.250", "el importe total es 1.250 euros", encoder=BIG, locale="es"
    )
    assert [a.support for a in spanish.anchors if a.kind == "numeral"] == [1.0]


# --- the receipt names a word, not a fragment -----------------------------


def test_receipts_never_point_at_punctuation() -> None:
    # The FakeEncoder splits punctuation into its own tokens, exactly like a
    # BERT-family tokenizer. Before candidate filtering, a period or a quote
    # could win the max on a weak word and the receipt would name it. A
    # receipt whose evidence is punctuation helps nobody, so it is banned.
    profile = run(
        "Foxglove BioSciences reported strong momentum across segments.",
        [("doc#p1", "Its subsidiary Willowbark Labs recorded a net loss.")],
    )
    for anchor in profile.anchors:
        if anchor.evidence_text is not None:
            assert any(ch.isalnum() for ch in anchor.evidence_text), anchor.receipt()


def test_evidence_is_expanded_to_the_containing_word() -> None:
    # The winning token can be a subword fragment ('s' out of "Foxglove's").
    # The receipt must name the whole word a human would point at, and the
    # expanded evidence must still be a real slice of the source.
    source = "Foxglove's Q4 revenue was strong."
    profile = run("Foxgloves revenue grew.", [("doc#p1", source)])
    for anchor in profile.anchors:
        if anchor.evidence_span is None:
            continue
        start, end = anchor.evidence_span
        assert source[start:end] == anchor.evidence_text
        assert anchor.evidence_text not in {"s", "'"}
        assert " " not in anchor.evidence_text or anchor.evidence_text.strip()


def test_receipt_line_is_readable() -> None:
    # No literal tabs: the line renders the same in a terminal, a pandas cell
    # and a log file. Word, support, evidence, in that order.
    weakest = run(INVOICE_PERTURBED).weakest[0]
    line = weakest.receipt()
    assert "\t" not in line
    assert "support 0.00" in line
    assert "nearest in" in line
