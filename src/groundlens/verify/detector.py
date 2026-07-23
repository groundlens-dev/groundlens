"""The model-based second-stage detector.

:class:`SampleConsistency` ties a text generator, a sampling strategy and a
scorer together, and returns a Groundlens :class:`~groundlens.check.Check`, the
same result type SGI and DGI return, so downstream code renders one vocabulary.

:class:`SelfCheckNLI` and :class:`ParaphraseCheck` are presets. ``SelfCheckNLI``
reproduces SelfCheckGPT-NLI (resample the model, score with NLI). ``ParaphraseCheck``
uses the paraphrase sampler, which front-loads the signal at a low sample budget.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from groundlens.check import Check, check_for_verification
from groundlens.verify import samplers
from groundlens.verify.scorers import EmbeddingScorer, NLIScorer

if TYPE_CHECKING:
    from groundlens.verify._base import Scorer, TextGenerator

_SAMPLERS = {"resample": samplers.resample, "paraphrase": samplers.paraphrase}
_BASE_NAME = {"resample": "selfcheck", "paraphrase": "paraphrase"}


@dataclass(frozen=True, slots=True)
class Verification:
    """The full, auditable outcome of a second-stage check.

    ``check`` is the plain-language :class:`~groundlens.check.Check` you act on;
    the other fields are the audit trail, since a stochastic stage inside an
    auditable library must expose what it saw.

    Attributes:
        check: The plain-language reading (same type as SGI/DGI).
        answer: The primary answer that was checked.
        samples: The candidate answers it was compared against.
        consistency: Agreement in ``[0, 1]`` (``1 - inconsistency``).
        method: e.g. ``"selfcheck_nli"``, ``"paraphrase_nli"``.
        seconds: Wall-clock of the check.
        seed: Seed used for generation, when set (for reproducibility).
    """

    check: Check
    answer: str
    samples: tuple[str, ...]
    consistency: float
    method: str
    seconds: float
    seed: int | None = None


class SampleConsistency:
    """Generic second-stage checker: generator + sampler + scorer -> Check.

    Args:
        model: HF model id for the bundled local generator. Ignored if
            ``generator`` is given; required otherwise.
        generator: Any :class:`~groundlens.verify.TextGenerator`. Pass this to
            use an API model or your own client instead of the local default.
        sampler: ``"resample"`` (SelfCheck-style) or ``"paraphrase"``.
        scorer: ``"nli"`` (validated, needs the extra), ``"embedding"`` (no extra),
            or any object implementing :class:`~groundlens.verify.Scorer`.
        n_samples: Number of samples to compare against.
        seed: Optional generation seed for reproducibility.
        **generator_kwargs: Forwarded to the local generator (e.g.
            ``load_in_4bit``, ``max_new_tokens``, ``batch_sequences``).
    """

    def __init__(
        self,
        model: str | None = None,
        *,
        generator: TextGenerator | None = None,
        sampler: str = "resample",
        scorer: str | Scorer = "nli",
        n_samples: int = 7,
        seed: int | None = None,
        **generator_kwargs: object,
    ) -> None:
        if sampler not in _SAMPLERS:
            msg = f"sampler must be one of {sorted(_SAMPLERS)}, got {sampler!r}."
            raise ValueError(msg)
        self._sampler_name = sampler
        self._sampler = _SAMPLERS[sampler]
        self.n_samples = n_samples
        self.seed = seed

        if isinstance(scorer, str):
            if scorer == "nli":
                self._scorer: Scorer = NLIScorer()
            elif scorer == "embedding":
                self._scorer = EmbeddingScorer()
            else:
                msg = f"scorer must be 'nli', 'embedding', or a Scorer, got {scorer!r}."
                raise ValueError(msg)
            scorer_name = scorer
        else:
            self._scorer = scorer
            scorer_name = getattr(scorer, "name", type(scorer).__name__.lower())

        if generator is not None:
            self._generator = generator
        elif model is not None:
            from groundlens.providers.hf import HFTextGenerator

            self._generator = HFTextGenerator(model, seed=seed, **generator_kwargs)  # type: ignore[arg-type]
        else:
            msg = "Provide either model=... (bundled local generator) or generator=...."
            raise ValueError(msg)

        self._method = f"{_BASE_NAME[sampler]}_{scorer_name}"

    def verify(self, question: str, answer: str | None = None) -> Verification:
        """Run the check and return the full auditable :class:`Verification`."""
        start = time.perf_counter()
        gen = self._generator
        primary = (
            answer if (answer is not None and answer.strip()) else samplers.answer(gen, question)
        )
        samples = self._sampler(gen, question, self.n_samples)
        inconsistency = float(self._scorer.inconsistency(question, primary, samples))
        consistency = max(0.0, min(1.0, 1.0 - inconsistency))
        reading = check_for_verification(consistency, method=self._method, n_samples=len(samples))
        return Verification(
            check=reading,
            answer=primary,
            samples=tuple(samples),
            consistency=consistency,
            method=self._method,
            seconds=time.perf_counter() - start,
            seed=self.seed,
        )

    def check(self, question: str, answer: str | None = None) -> Check:
        """Run the check and return just the plain-language :class:`Check`."""
        return self.verify(question, answer).check


class SelfCheckNLI(SampleConsistency):
    """Preset: resample the model and score with NLI (reproduces SelfCheckGPT-NLI)."""

    def __init__(self, model: str | None = None, **kwargs: object) -> None:
        super().__init__(model, sampler="resample", scorer="nli", **kwargs)  # type: ignore[arg-type]


class ParaphraseCheck(SampleConsistency):
    """Preset: reword the question and score with NLI (low-budget, front-loaded signal)."""

    def __init__(self, model: str | None = None, **kwargs: object) -> None:
        super().__init__(model, sampler="paraphrase", scorer="nli", **kwargs)  # type: ignore[arg-type]
