from __future__ import annotations

from decimal import Decimal

import pytest

from groundlens._numerals import (
    find_numerals,
    format_decimal,
    locale,
    matches,
    value_set,
)
from groundlens._text import is_normalised, normalised

UND = locale("und")
EN = locale("en")
ES = locale("es")


def vals(text: str, profile=UND) -> list[list[str]]:
    return [[format_decimal(r) for r in n.readings] for n in find_numerals(text, profile)]


# --- the thing the whole product rests on ---------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10,000", "10000"),
        ("10000", "10000"),
        ("$10,000", "10000"),
        ("10 000", "10000"),
        ("10 000", "10000"),  # narrow no-break space
        ("EUR 10.000", "10000"),
        ("10'000", "10000"),  # Swiss
        ("１０，０００", "10000"),  # full-width, folded by NFKC
    ],
)
def test_ten_thousand_is_ten_thousand_however_you_write_it(text: str, expected: str) -> None:
    readings = find_numerals(normalised(text), UND)[0].readings
    assert Decimal(expected) in readings


def test_ten_is_not_a_hundred() -> None:
    context_values = value_set(["the total amount due is 10,000 dollars"], UND)
    wrong = find_numerals("the total is 1,000 dollars", UND)[0]
    right = find_numerals("the total is 10,000 dollars", UND)[0]
    assert not matches(wrong, context_values)
    assert matches(right, context_values)


def test_format_variant_is_not_a_defect() -> None:
    context_values = value_set(["the total amount due is 10,000 dollars"], UND)
    for variant in ("10000", "10 000", "$10,000", "10.000"):
        numeral = find_numerals(normalised(f"the total is {variant} dollars"), UND)[0]
        assert matches(numeral, context_values), variant


# --- ambiguity is preserved, never guessed --------------------------------


def test_unknown_locale_keeps_both_readings() -> None:
    numeral = find_numerals("1.234", UND)[0]
    assert set(numeral.readings) == {Decimal("1234"), Decimal("1.234")}
    assert numeral.notes == ("grouping_vs_decimal",)
    assert numeral.ambiguous


def test_known_locale_resolves_it() -> None:
    assert vals("1.234", ES) == [["1234"]]
    assert vals("1.234", EN) == [["1.234"]]
    assert vals("1,234", ES) == [["1.234"]]
    assert vals("1,234", EN) == [["1234"]]


def test_the_bug_that_would_have_shipped() -> None:
    """`1.000,50` must be 1000.50, not 1.0005.

    The notebook's 12-line parser strips commas whenever it sees one, which
    silently returns 1.0005 and then reports a false alarm against a source that
    literally contains the number.
    """
    assert vals("1.000,50") == [["1000.5"]]
    assert vals("1,000.50") == [["1000.5"]]
    # the notebook's parser returns Decimal("1.0005") here
    assert Decimal("1.0005") not in find_numerals("1.000,50", UND)[0].readings


def test_repeated_separator_can_only_be_grouping() -> None:
    assert vals("1.234.567") == [["1234567"]]
    assert find_numerals("1.234.567", UND)[0].notes == ("separator_repeated",)


def test_non_three_digit_tail_is_a_decimal() -> None:
    assert vals("1.5") == [["1.5"]]
    assert vals("3.14159") == [["3.14159"]]


def test_ambiguous_numeral_matches_on_its_best_reading() -> None:
    context_values = value_set(["the fee is 1,234 euros"], UND)  # {1234, 1.234}
    assert matches(find_numerals("1.234", UND)[0], context_values)


# --- scope and safety -----------------------------------------------------


def test_single_digits_are_not_facts() -> None:
    assert find_numerals("step 1 then step 2", UND) == []


def test_negatives() -> None:
    assert vals("-1,500", EN) == [["-1500"]]
    assert vals("(1,500)", EN) == [["-1500"]]
    assert vals("−1,500", EN) == [["-1500"]]  # U+2212
    # under an unknown locale the sign survives on every reading
    assert all(r < 0 for r in find_numerals("-1,500", UND)[0].readings)


def test_percent_and_currency_do_not_change_the_value() -> None:
    assert vals("3.5%") == [["3.5"]]
    assert vals("€1,250", EN) == [["1250"]]
    assert vals("1.250 EUR", ES) == [["1250"]]


def test_locale_never_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LC_ALL", "es_ES.UTF-8")
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    assert vals("1,234", EN) == [["1234"]]


def test_pattern_does_not_backtrack_on_adversarial_input() -> None:
    import time

    hostile = "1" + ",123" * 400 + "x"
    start = time.perf_counter()
    find_numerals(hostile, UND)
    assert time.perf_counter() - start < 1.0


def test_spans_point_at_the_numeral() -> None:
    text = "a total of 10,000 dollars"
    numeral = find_numerals(text, UND)[0]
    start, end = numeral.span
    assert text[start:end].strip() == "10,000"


# --- normalisation --------------------------------------------------------


def test_normalisation_is_idempotent() -> None:
    for text in ("  a\r\nb\u200b  c ", "1 234,50", "ﬁle", "１０"):
        once = normalised(text)
        assert normalised(once) == once
        assert is_normalised(once)


def test_invisibles_are_deleted() -> None:
    assert normalised("10\u200b,\u200b000") == "10,000"


# --- a sign must touch its number --------------------------------------


def test_spaced_hyphen_is_punctuation_not_minus() -> None:
    # Real case from the Berkshire 2024 letter: "our sole payment - $101,755".
    # The dash is prose punctuation. Reading it as a minus made the exact
    # channel compare -101755 against a claimed 101755 and report a fabrication
    # that was not there.
    found = find_numerals("our sole payment - $101,755 or 10 cents", locale("en"))
    amounts = [r for n in found for r in n.readings]
    assert Decimal("101755") in amounts
    assert Decimal("-101755") not in amounts


def test_adjacent_sign_is_still_negative() -> None:
    found = find_numerals("a swing of -$101,755 on the year", locale("en"))
    assert Decimal("-101755") in [r for n in found for r in n.readings]
    found = find_numerals("a delta of -1,234 units", locale("en"))
    assert Decimal("-1234") in [r for n in found for r in n.readings]


def test_ranges_do_not_negate_their_second_number() -> None:
    found = find_numerals("see pages 45 - 78 for detail", locale("en"))
    values = [r for n in found for r in n.readings]
    assert Decimal("78") in values
    assert Decimal("-78") not in values


def test_currency_with_space_still_parses() -> None:
    # Docling writes "$ 5,428" for table cells; the space after the currency
    # symbol stays legal.
    found = find_numerals("earnings were $ 5,428 for the period", locale("en"))
    assert Decimal("5428") in [r for n in found for r in n.readings]
