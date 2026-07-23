"""Groundlens second stage: model-based consistency checks.

This is the model-based stage the deterministic first stage (SGI / DGI) hands off
to. It is optional and kept out of the core import path: ``import groundlens``
never loads a model, and even importing this subpackage does not, the heavy
libraries load lazily on first use.

Install the extra to use it::

    pip install "groundlens[verify]"

Quick start::

    >>> from groundlens.verify import SelfCheckNLI
    >>> checker = SelfCheckNLI(model="Qwen/Qwen2.5-7B-Instruct")
    >>> reading = checker.check("What is the capital of Spain?", "Madrid")
    >>> reading.level                      # "ok" / "review" / "risk"
    'ok'

Only spend model calls on the cases geometry could not settle::

    >>> from groundlens.verify import two_stage
    >>> result = two_stage(
    ...     question="What is the capital of Spain?",
    ...     answer="Madrid",
    ...     context="Spain is a country in Europe. Its capital is Madrid.",
    ...     model="Qwen/Qwen2.5-7B-Instruct",
    ... )
    >>> result.escalated                   # False: SGI settled it, no model call
    False
    >>> print(result.final)                # the CHECK to act on

The pieces are swappable: pass any :class:`TextGenerator` (an API client wrapper,
say) instead of the bundled local one, and choose ``scorer="nli"`` (validated,
needs the extra) or ``scorer="embedding"`` (runs on the core install).

Reference:
    Manakul, Liusie, Gales (2023). SelfCheckGPT: Zero-Resource Black-Box
    Hallucination Detection for Generative LLMs. EMNLP 2023. arXiv:2303.08896.
    ``SelfCheckNLI`` reproduces their NLI variant (92.50 AUC-PR on WikiBio-GPT3).
"""

from __future__ import annotations

from groundlens.verify import samplers
from groundlens.verify._base import Scorer, TextGenerator
from groundlens.verify.detector import (
    ParaphraseCheck,
    SampleConsistency,
    SelfCheckNLI,
    Verification,
)
from groundlens.verify.generators import (
    AnthropicGenerator,
    GeminiGenerator,
    OpenAIGenerator,
)
from groundlens.verify.pipeline import TwoStageResult, two_stage
from groundlens.verify.scorers import EmbeddingScorer, NLIScorer

__all__ = [
    "AnthropicGenerator",
    "EmbeddingScorer",
    "GeminiGenerator",
    "NLIScorer",
    "OpenAIGenerator",
    "ParaphraseCheck",
    "SampleConsistency",
    "Scorer",
    "SelfCheckNLI",
    "TextGenerator",
    "TwoStageResult",
    "Verification",
    "samplers",
    "two_stage",
]
