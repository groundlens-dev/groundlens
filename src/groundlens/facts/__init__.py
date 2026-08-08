"""Deterministic fact extraction, normalisation and matching.

Three units, deliberately separable:

- :mod:`groundlens.facts.normalise` turns a raw substring into a canonical
  string under a locale profile.  Testable on its own, no text scanning.
- :mod:`groundlens.facts.extract` finds the checkable claims in NFKC-normalised
  text and returns :class:`~groundlens.types.Fact` values with char spans.
- :mod:`groundlens.facts.match` decides each fact against evidence and returns
  :class:`~groundlens.types.Match` values with an evidence id and span.

Nothing here imports numpy, torch or any model.  Stdlib ``re`` only.
"""

from __future__ import annotations

from groundlens.facts.config import DEFAULT_MAX_FACTS, ExtractConfig, MatchConfig
from groundlens.facts.extract import EXTRACTOR_VERSION, extract_facts
from groundlens.facts.match import match_facts
from groundlens.facts.normalise import Normalisation

__all__ = [
    "DEFAULT_MAX_FACTS",
    "EXTRACTOR_VERSION",
    "ExtractConfig",
    "MatchConfig",
    "Normalisation",
    "extract_facts",
    "match_facts",
]
