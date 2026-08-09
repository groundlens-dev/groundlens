"""Cardinals written as words.

The positive cases are one line each. The bulk of this file is negative: the
constructions the extractor is required to *refuse*. On this corpus a NUMBER
invented on clean traffic costs more than a NUMBER missed on a defect, so every
refusal below is part of the specification, not a limitation being tolerated.
"""

from __future__ import annotations

from datetime import date

import pytest

from .conftest import make_profile

REF = date(2026, 2, 10)


@pytest.fixture(scope="module")
def gb():
    return make_profile(
        "en-gb", decimal_separator=".", group_separator=",", date_order="DMY", currency="GBP"
    )


@pytest.fixture(scope="module")
def eu():
    return make_profile(
        "eu-es", decimal_separator=",", group_separator=".", date_order="DMY", currency="EUR"
    )


def numbers(text, profile):
    from groundlens.facts import extract_facts

    return [
        fact
        for fact in extract_facts(text, locale=profile, reference_date=REF)
        if fact.kind.value == "number"
    ]


def values(text, profile):
    return [fact.normalised for fact in numbers(text, profile)]


# ---------------------------------------------------------------------------
# the point of the exercise: word and digit land on the same string
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("word", "digits"),
    [
        ("zero", "0"),
        ("two", "2"),
        ("three", "3"),
        ("nine", "9"),
        ("ten", "10"),
        ("eleven", "11"),
        ("nineteen", "19"),
        ("twenty", "20"),
        ("fifty", "50"),
        ("ninety", "90"),
    ],
)
def test_english_cardinal_normalises_like_its_digits(gb, word, digits):
    assert values(f"We counted {word} exceptions.", gb) == [digits]
    assert values(f"We counted {digits} exceptions.", gb) == [digits]


@pytest.mark.parametrize(
    ("word", "digits"),
    [
        ("cero", "0"),
        ("dos", "2"),
        ("tres", "3"),
        ("seis", "6"),
        ("diez", "10"),
        ("quince", "15"),
        ("dieciséis", "16"),
        ("dieciseis", "16"),
        ("veinte", "20"),
        ("treinta", "30"),
        ("noventa", "90"),
    ],
)
def test_spanish_cardinal_normalises_like_its_digits(eu, word, digits):
    assert values(f"Se registraron {word} incidencias.", eu) == [digits]


def test_capitalised_at_the_start_of_a_sentence_is_still_a_count(gb):
    assert values("Three sanctions matches were returned.", gb) == ["3"]


def test_the_span_slices_back_out_of_the_text(gb):
    text = "We counted seventeen exceptions."
    fact = numbers(text, gb)[0]
    assert fact.raw == text[fact.span[0] : fact.span[1]] == "seventeen"


def test_a_word_cardinal_records_how_it_was_written(gb):
    assert dict(numbers("We counted three exceptions.", gb)[0].attrs)["numeral"] == "word"


def test_a_digit_cardinal_carries_no_numeral_attribute(gb):
    assert "numeral" not in dict(numbers("We counted 3 exceptions.", gb)[0].attrs)


# ---------------------------------------------------------------------------
# refusals: English "one"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "One of the reasons the file was held is documentation.",
        "The one that failed was reopened.",
        "One must file the return before the deadline.",
        "They were sent to one another for review.",
        "There is one exception on file.",
    ],
)
def test_english_one_is_never_a_number(gb, text):
    """Pronoun, impersonal subject, quantifier, fixed phrase — and a real count.

    The count is refused with the rest. Telling the five apart needs syntax this
    library does not have, and four wrong answers out of five is not a trade
    worth making for the fifth.
    """
    assert values(text, gb) == []


# ---------------------------------------------------------------------------
# refusals: Spanish "un" / "una" / "uno", and the "once" homograph
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Uno de los motivos es la documentación.",
        "Se recibió un expediente incompleto.",
        "Se recibió una reclamación.",
    ],
)
def test_spanish_one_is_never_a_number(eu, text):
    assert values(text, eu) == []


def test_english_once_is_not_spanish_eleven(gb, eu):
    """Both lexicons are always live, so this homograph has to be given up.

    The cost is the second assertion: a real Spanish eleven is missed too.
    """
    assert values("The statement is issued once a year.", gb) == []
    assert values("El extracto se emite once veces.", eu) == []


# ---------------------------------------------------------------------------
# refusals: approximate quantifiers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "A couple of files were late.",
        "A few exceptions were noted.",
        "Several accounts were reviewed.",
        "Se revisaron unas cuantas cuentas.",
        "Se revisó una docena de expedientes.",
    ],
)
def test_approximate_quantifiers_are_not_counts(gb, text):
    assert values(text, gb) == []


# ---------------------------------------------------------------------------
# refusals: ordinals and fractions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "No charge applies after the third year.",
        "The twenty-first review was the last.",
        "The twenty first review was the last.",
        "Two-thirds of the files passed.",
        "Two thirds of the files passed.",
        "One half of the balance is due.",
        "El tercio restante se abona después.",
        "El primer expediente fue archivado.",
    ],
)
def test_ordinals_and_fractions_are_not_counts(gb, text):
    assert values(text, gb) == []


def test_an_ordinal_before_a_cardinal_does_not_block_it(gb):
    """ "the first three years" is the count three; only a trailing tail blocks."""
    assert values("A charge applies for the first three years of the loan.", gb) == ["3"]


# ---------------------------------------------------------------------------
# refusals: compounds and scale words
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "There are twenty-three open items.",
        "There are twenty three open items.",
        "Se abrieron treinta y dos expedientes.",
        "There are thirty and four open items.",
    ],
)
def test_compounds_are_refused_rather_than_read_as_their_first_element(gb, text):
    """Emitting 20 for "twenty-three" would be a confidently wrong value."""
    assert values(text, gb) == []


@pytest.mark.parametrize(
    "text",
    [
        "The fee is three hundred.",
        "Three thousand files were reviewed.",
        "Se revisaron tres mil expedientes.",
        "Se revisaron dos millones de registros.",
    ],
)
def test_a_scale_word_after_a_cardinal_blocks_it(gb, text):
    assert values(text, gb) == []


# ---------------------------------------------------------------------------
# refusals: upper case, and units that belong to another kind
# ---------------------------------------------------------------------------


def test_an_upper_cased_token_is_read_as_an_identifier_not_a_count(gb):
    assert values("The DOS export was rebuilt.", gb) == []


@pytest.mark.parametrize(
    "text",
    [
        "The rate is three percent.",
        "The rate is three per cent.",
        "La tasa es tres por ciento.",
        "The fee is three euros.",
        "The fee is three EUR.",
        "The fee is EUR three.",
    ],
)
def test_a_word_cardinal_carrying_a_unit_is_dropped_not_emitted_as_a_bare_number(gb, text):
    """``3 %`` is a PERCENT and ``3 EUR`` is a CURRENCY.

    Emitting a bare NUMBER for the spelled-out form would put the two spellings
    of one claim into different kinds, where they can never match each other.
    Dropping the word form keeps them merely absent instead of contradictory.
    """
    assert values(text, gb) == []


def test_a_duration_unit_does_not_block_the_count(gb):
    """The one unit that is kept, and the reason is a canary.

    "the first five years" against "the first three years" is asked for as
    ``fact.contradicted.number``, so a cardinal before a duration unit stays a
    NUMBER. The digit form of the same phrase is a DURATION; that asymmetry is
    deliberate and is recorded here so it cannot be "fixed" by accident.
    """
    assert values("A charge applies for the first three years.", gb) == ["3"]
    assert values("A charge applies for the first 3 years.", gb) == []


# ---------------------------------------------------------------------------
# the words must not disturb what was already extracted
# ---------------------------------------------------------------------------


def test_a_month_name_is_still_a_date(gb):
    from groundlens.facts import extract_facts

    facts = extract_facts("Due 3 March 2026.", locale=gb, reference_date=REF)
    kinds = [f.kind.value for f in facts]
    assert "date" in kinds


def test_extraction_is_repeatable(gb):
    text = "We counted three exceptions and seven overrides."
    assert values(text, gb) == values(text, gb) == ["3", "7"]
