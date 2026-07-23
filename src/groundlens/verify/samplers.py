"""Sampling strategies for the second stage.

Two ways to draw the samples an answer is checked against:

- :func:`resample` -- ask the same question again with sampling on. This is what
  SelfCheckGPT does: variation comes from the decoding temperature.
- :func:`paraphrase` -- reword the question and answer each rewording once.
  Variation comes from the input. It front-loads the signal (one or two
  rewordings carry most of it) but saturates, since a question has only so many
  genuinely different phrasings.

Both return a list of candidate answers to compare against the primary answer.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from groundlens.verify._base import TextGenerator

ANSWER_PROMPT = (
    "Answer the question with only the answer, as briefly as possible "
    "(a few words, no full sentence).\nQuestion: {q}\nAnswer:"
)
REWRITE_PROMPT = (
    "Rewrite the following question in {k} different ways that keep the EXACT same "
    "meaning and the same answer. Return each rewrite on its own line, numbered "
    "1..{k}, nothing else.\nQuestion: {q}"
)

_NUMBER_PREFIX = re.compile(r"^\s*\d+[\).\:\-]\s*")


def answer(generator: TextGenerator, question: str) -> str:
    """Draw a single primary answer to ``question``."""
    return generator.generate(ANSWER_PROMPT.format(q=question), 1)[0]


def resample(generator: TextGenerator, question: str, n: int) -> list[str]:
    """Draw ``n`` resampled answers to the same question (SelfCheck-style)."""
    return generator.generate(ANSWER_PROMPT.format(q=question), n)


def paraphrase(generator: TextGenerator, question: str, n: int) -> list[str]:
    """Reword ``question`` ``n`` ways and answer each once."""
    raw = generator.generate(REWRITE_PROMPT.format(k=n, q=question), 1)[0]
    variants = [_NUMBER_PREFIX.sub("", line).strip() for line in raw.splitlines() if line.strip()]
    variants = variants[:n]
    while len(variants) < n:  # if the model gave too few, pad with the original
        variants.append(question)
    return generator.generate_many([ANSWER_PROMPT.format(q=v) for v in variants])
