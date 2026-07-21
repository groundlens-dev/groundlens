"""Protocols for the model-based second stage.

Two small seams keep the second stage model-agnostic:

- :class:`TextGenerator` -- anything that can produce samples from a prompt. The
  bundled :class:`groundlens.providers.hf.HFTextGenerator` implements it, but so
  can a thin wrapper around an API client, so the second stage is not tied to
  any vendor or to Hugging Face.
- :class:`Scorer` -- anything that turns (question, answer, samples) into an
  inconsistency in ``[0.0, 1.0]`` where higher means less self-consistent.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TextGenerator(Protocol):
    """A source of stochastic completions used by the samplers."""

    def generate(self, prompt: str, n: int = 1) -> list[str]:
        """Return ``n`` sampled completions of a single prompt."""
        ...

    def generate_many(self, prompts: list[str]) -> list[str]:
        """Return one sampled completion for each of ``prompts``."""
        ...


@runtime_checkable
class Scorer(Protocol):
    """Turns an answer and its samples into an inconsistency score in ``[0, 1]``."""

    def inconsistency(self, question: str, answer: str, samples: list[str]) -> float:
        """Higher means the answer disagrees more with its samples."""
        ...
