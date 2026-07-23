"""Cover the deprecation shim re-export and the single-answer sampler."""

from __future__ import annotations

from groundlens.verify import samplers


def test_two_stage_shim_reexports() -> None:
    from groundlens.verify.two_stage import TwoStageResult, two_stage

    assert callable(two_stage)
    assert TwoStageResult is not None


def test_answer_draws_one_primary() -> None:
    class Gen:
        def generate(self, prompt: str, n: int = 1) -> list[str]:
            assert n == 1
            return ["Madrid"]

        def generate_many(self, prompts: list[str]) -> list[str]:
            return []

    assert samplers.answer(Gen(), "Capital of Spain?") == "Madrid"
