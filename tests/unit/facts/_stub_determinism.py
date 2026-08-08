"""Stand-in for ``groundlens.determinism`` (contract section 5).

Installed by ``conftest.py`` **only when the real module is absent**.

This file doubles as the executable statement of exactly what
``groundlens.facts`` needs from the determinism module.  The extractor reads
three string fields off a ``LocaleProfile`` and nothing else, through the alias
lookup in ``groundlens.facts.normalise``; if the real profile spells them
differently, the alias lists there are the single place to update.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LocaleProfile:
    name: str
    decimal_separator: str = "."
    group_separator: str = ","
    date_order: str = "DMY"
    currency: str | None = None


PROFILES: dict[str, LocaleProfile] = {
    "eu-es": LocaleProfile("eu-es", ",", ".", "DMY", "EUR"),
    "eu-de": LocaleProfile("eu-de", ",", ".", "DMY", "EUR"),
    "eu-fr": LocaleProfile("eu-fr", ",", " ", "DMY", "EUR"),
    "en-gb": LocaleProfile("en-gb", ".", ",", "DMY", "GBP"),
    "en-us": LocaleProfile("en-us", ".", ",", "MDY", "USD"),
    "iso": LocaleProfile("iso", ".", " ", "YMD", None),
}


def get_locale_profile(name: str) -> LocaleProfile:
    return PROFILES[name]


def normalise_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def parse_decimal(text: str, profile: LocaleProfile) -> Decimal:
    cleaned = text.strip().replace(profile.group_separator, "")
    if profile.decimal_separator != ".":
        cleaned = cleaned.replace(profile.decimal_separator, ".")
    return Decimal(cleaned)
