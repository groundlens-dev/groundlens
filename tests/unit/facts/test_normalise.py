"""Unit tests for the value normaliser, exercised without the extractor."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from .conftest import make_profile


@pytest.fixture(scope="module")
def eu():
    return make_profile(
        "eu-es", decimal_separator=",", group_separator=".", date_order="DMY", currency="EUR"
    )


@pytest.fixture(scope="module")
def us():
    return make_profile(
        "en-us", decimal_separator=".", group_separator=",", date_order="MDY", currency="USD"
    )


@pytest.fixture(scope="module")
def gb():
    return make_profile(
        "en-gb", decimal_separator=".", group_separator=",", date_order="DMY", currency="GBP"
    )


# ---------------------------------------------------------------------------
# format_decimal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1000", "1000"),
        ("1000.00", "1000"),
        ("1E+3", "1000"),
        ("0.1", "0.1"),
        ("-0.0", "0"),
        ("-3.250", "-3.25"),
        ("0.000", "0"),
        ("1234567890123456789", "1234567890123456789"),
    ],
)
def test_format_decimal_is_plain_and_trimmed(value, expected):
    from groundlens.facts.normalise import format_decimal

    assert format_decimal(Decimal(value)) == expected


def test_no_float_anywhere_in_the_public_surface(eu):
    from groundlens.facts import normalise as module

    results = [
        module.normalise_number("1.000", eu),
        module.normalise_currency("1.000", "EUR", eu),
        module.normalise_percent("2,5", eu),
        module.normalise_date("3 de marzo de 2026", eu),
        module.normalise_duration("30 días", eu),
        module.normalise_citation("Art. 12"),
    ]
    for result in results:
        assert isinstance(result.value, str)
        for key, value in result.attrs:
            assert isinstance(key, str)
            assert isinstance(value, str)


# ---------------------------------------------------------------------------
# separators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.000", "1000"),
        ("1 000,00", "1000"),
        ("1.500,75", "1500.75"),
        ("1000", "1000"),
        ("0,5", "0.5"),
        ("1.234.567,89", "1234567.89"),
    ],
)
def test_eu_number_readings(eu, raw, expected):
    from groundlens.facts.normalise import normalise_number

    assert normalise_number(raw, eu).value == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,000", "1000"),
        ("1,000.00", "1000"),
        ("1000.5", "1000.5"),
        ("0.500", "0.5"),
        ("1,234,567.89", "1234567.89"),
    ],
)
def test_us_number_readings(us, raw, expected):
    from groundlens.facts.normalise import normalise_number

    assert normalise_number(raw, us).value == expected


def test_the_four_required_currency_forms_agree_under_their_profiles(eu, us):
    from groundlens.facts.normalise import normalise_currency

    assert normalise_currency("1,000", "EUR", eu).value == "EUR 1000"
    assert normalise_currency("1.000", "EUR", eu).value == "EUR 1000"
    assert normalise_currency("1000", "€", eu).value == "EUR 1000"
    assert normalise_currency("1 000,00", "EUR", eu).value == "EUR 1000"
    assert normalise_currency("1,000.00", "USD", us).value == "USD 1000"


def test_comma_with_three_digits_on_money_is_flagged_not_silent(eu):
    from groundlens.facts.normalise import normalise_currency

    result = normalise_currency("1,000", "EUR", eu)
    assert result.value == "EUR 1000"
    assert "grouping_vs_decimal" in result.ambiguities


def test_a_plain_number_keeps_the_literal_profile_reading(eu):
    """No currency to make a three-digit fraction implausible, so no re-reading."""
    from groundlens.facts.normalise import normalise_number

    result = normalise_number("1,000", eu)
    assert result.value == "1"
    assert "grouping_vs_decimal" in result.ambiguities


def test_zero_point_five_hundred_is_never_five_hundred(us):
    from groundlens.facts.normalise import normalise_currency

    assert normalise_currency("0.500", "USD", us).value == "USD 0.5"


def test_malformed_grouping_is_reported(us):
    from groundlens.facts.normalise import normalise_number

    result = normalise_number("1,00,000", us)
    assert "grouping_malformed" in result.ambiguities


def test_unparsable_input(us):
    from groundlens.facts.normalise import normalise_number

    assert normalise_number("abc", us).value == ""


def test_negative_and_accounting_negative(us):
    from groundlens.facts.normalise import normalise_number

    assert normalise_number("-1,250.50", us).value == "-1250.5"
    assert normalise_number("(1,250.50)", us).value == "-1250.5"


# ---------------------------------------------------------------------------
# currency resolution
# ---------------------------------------------------------------------------


def test_unambiguous_symbol(eu):
    from groundlens.facts.normalise import resolve_currency

    assert resolve_currency("€", eu) == ("EUR", ())


def test_dollar_sign_uses_the_profile_only_when_plausible(us, eu):
    from groundlens.facts.normalise import resolve_currency

    assert resolve_currency("$", us) == ("USD", ())
    code, ambiguities = resolve_currency("$", eu)
    assert code == "$"
    assert ambiguities == ("currency_symbol_ambiguous",)


def test_jpy_has_no_minor_unit(gb):
    from groundlens.facts.normalise import normalise_currency

    assert normalise_currency("1,000", "JPY", gb).value == "JPY 1000"


def test_multiplier(us):
    from groundlens.facts.normalise import normalise_currency

    result = normalise_currency("3.5", "$", us, multiplier="million")
    assert result.value == "USD 3500000"


def test_spanish_billion_is_flagged(eu):
    from groundlens.facts.normalise import normalise_number

    result = normalise_number("2", eu, multiplier="billón")
    assert result.value == "2000000000000"
    assert "multiplier_ambiguous" in result.ambiguities


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["3 March 2026", "03/03/2026", "2026-03-03", "3 de marzo de 2026", "March 3, 2026"],
)
def test_every_surface_form_of_one_date(gb, us, raw):
    from groundlens.facts.normalise import normalise_date

    profile = us if raw.startswith("March") else gb
    assert normalise_date(raw, profile).value == "2026-03-03"


def test_ambiguous_numeric_date_follows_the_profile_and_says_so(gb, us):
    from groundlens.facts.normalise import normalise_date

    dmy = normalise_date("03/04/2026", gb)
    mdy = normalise_date("03/04/2026", us)
    assert dmy.value == "2026-04-03"
    assert mdy.value == "2026-03-04"
    assert "date_order_ambiguous" in dmy.ambiguities
    assert dict(dmy.attrs)["date_ambiguous"] == "true"
    assert dict(dmy.attrs)["date_order"] == "DMY"


def test_unambiguous_numeric_date_is_not_flagged(gb):
    from groundlens.facts.normalise import normalise_date

    assert "date_order_ambiguous" not in normalise_date("25/12/2026", gb).ambiguities


def test_two_digit_year_is_flagged(gb):
    from groundlens.facts.normalise import normalise_date

    result = normalise_date("03/03/26", gb)
    assert result.value == "2026-03-03"
    assert "two_digit_year" in result.ambiguities


def test_missing_year_without_an_anchor_stays_partial(gb):
    from groundlens.facts.normalise import normalise_date

    assert normalise_date("3 March", gb).value == "--03-03"


def test_missing_year_resolves_forward_from_the_anchor(gb):
    from groundlens.facts.normalise import normalise_date

    result = normalise_date("3 March", gb, resolve_year_from=date(2026, 4, 1))
    assert result.value == "2027-03-03"
    assert "year_inferred" in result.ambiguities


def test_impossible_date_is_refused(gb):
    from groundlens.facts.normalise import normalise_date

    result = normalise_date("31/02/2026", gb)
    assert result.value == ""
    assert "invalid_date" in result.ambiguities


# ---------------------------------------------------------------------------
# durations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30 days", "P30D"),
        ("2 weeks", "P14D"),
        ("3 months", "P3M"),
        ("1 year", "P1Y"),
        ("24 hours", "PT24H"),
        ("90 minutes", "PT90M"),
        ("1 quarter", "P3M"),
        ("1 year and 6 months", "P1Y6M"),
        ("30 días", "P30D"),
        ("2 semanas", "P14D"),
        ("3 meses", "P3M"),
        ("1 año", "P1Y"),
    ],
)
def test_duration_canonical_forms(gb, raw, expected):
    from groundlens.facts.normalise import normalise_duration

    assert normalise_duration(raw, gb).value == expected


def test_months_are_never_converted_to_days(gb):
    from groundlens.facts.normalise import normalise_duration

    assert normalise_duration("1 month", gb).value == "P1M"


def test_business_days_carry_their_basis(gb, eu):
    from groundlens.facts.normalise import normalise_duration

    assert dict(normalise_duration("30 business days", gb).attrs)["day_basis"] == "business"
    assert dict(normalise_duration("30 días hábiles", eu).attrs)["day_basis"] == "business"


def test_add_duration_calendar_arithmetic():
    from groundlens.facts.normalise import add_duration

    assert add_duration(date(2026, 1, 31), "P1M") == date(2026, 2, 28)
    assert add_duration(date(2026, 2, 10), "P30D") == date(2026, 3, 12)
    assert add_duration(date(2026, 2, 10), "P1Y") == date(2027, 2, 10)
    assert add_duration(date(2026, 2, 10), "not-a-duration") is None


# ---------------------------------------------------------------------------
# citations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Article 12", "ARTICLE 12"),
        ("art. 12", "ARTICLE 12"),
        ("artículo 12", "ARTICLE 12"),
        ("§4.2", "SECTION 4.2"),
        ("Reg. (EU) 2016/679", "REGULATION (EU) 2016/679"),
        ("Reglamento (UE) 2016/679", "REGULATION (EU) 2016/679"),
        ("EBA/GL/2020/06", "EBA/GL/2020/06"),
        ("[3]", "REF 3"),
        ("[3, 4]", "REF 3,4"),
    ],
)
def test_citation_canonical_forms(raw, expected):
    from groundlens.facts.normalise import normalise_citation

    assert normalise_citation(raw).value == expected


# ---------------------------------------------------------------------------
# profile accessors
# ---------------------------------------------------------------------------


def test_profile_accessors_have_defaults_for_an_unknown_shape():
    from groundlens.facts.normalise import (
        date_order_of,
        decimal_separator_of,
        group_separator_of,
    )

    class Bare:
        pass

    bare = Bare()
    assert decimal_separator_of(bare) == "."
    assert group_separator_of(bare) == ","
    assert date_order_of(bare) == "DMY"
