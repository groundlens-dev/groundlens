"""Fuzz the numeral path.

Not badge-chasing. This library reads two kinds of untrusted text by definition
-- model output and retrieved documents -- and the numeral parser is a regex
over both. `NUMBER_PATTERN` bounds digit-group repetition at 8 specifically
because an unbounded `+` backtracks quadratically on adversarial input. A fuzzer
is the only thing that actually holds that bound honest.

Properties asserted, all of which must survive any input:

* parsing never raises;
* every span returned is a real slice of the input;
* normalisation is idempotent, so spans stay meaningful;
* segmentation never loses or overlaps characters.

Run locally:  pip install atheris && python fuzz/fuzz_numerals.py
"""

import sys

import atheris

with atheris.instrument_imports():
    from groundlens._numerals import LOCALES, find_numerals, format_decimal
    from groundlens._text import normalised
    from groundlens._words import segment

PROFILES = [LOCALES[name] for name in ("und", "en", "es", "de", "ch")]


def one_input(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    profile = PROFILES[fdp.ConsumeIntInRange(0, len(PROFILES) - 1)]
    raw = fdp.ConsumeUnicodeNoSurrogates(4096)

    text = normalised(raw)
    if normalised(text) != text:
        raise AssertionError("normalised() is not idempotent")

    for numeral in find_numerals(text, profile):
        start, end = numeral.span
        if not (0 <= start < end <= len(text)):
            raise AssertionError(f"span {numeral.span} outside text of {len(text)}")
        if text[start:end] != numeral.text:
            raise AssertionError(f"span does not slice back: {text[start:end]!r} != {numeral.text!r}")
        if not numeral.readings:
            raise AssertionError("numeral emitted with no readings")
        for reading in numeral.readings:
            format_decimal(reading)

    previous_end = 0
    for unit in segment(text, profile):
        start, end = unit.span
        if start < previous_end:
            raise AssertionError(f"units overlap at {unit.span}")
        if text[start:end] != unit.text:
            raise AssertionError("unit span does not slice back")
        previous_end = end


def main() -> None:
    atheris.Setup(sys.argv, one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
