"""Sampler behavior: resample count, paraphrase parsing and padding."""

from __future__ import annotations

from groundlens.verify import samplers


class StubGen:
    """Minimal TextGenerator stub."""

    def generate(self, prompt: str, n: int = 1) -> list[str]:
        if "Rewrite" in prompt:
            return ["1. First way?\n2. Second way?\n3. Third way?"]
        return [f"answer{i}" for i in range(n)]

    def generate_many(self, prompts: list[str]) -> list[str]:
        return [f"pa{i}" for i in range(len(prompts))]


def test_resample_returns_n() -> None:
    assert len(samplers.resample(StubGen(), "Q?", 5)) == 5


def test_paraphrase_returns_n_answers() -> None:
    assert len(samplers.paraphrase(StubGen(), "Q?", 3)) == 3


def test_paraphrase_pads_when_model_returns_too_few() -> None:
    class Few(StubGen):
        def generate(self, prompt: str, n: int = 1) -> list[str]:
            if "Rewrite" in prompt:
                return ["1. only one rewrite?"]
            return ["x"]

    # even with a single rewrite, the answer count must equal n (padded with the original)
    assert len(samplers.paraphrase(Few(), "Q?", 3)) == 3
