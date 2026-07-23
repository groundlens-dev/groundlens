"""HFTextGenerator logic, exercised with stubs (no torch, no model download).

``_ensure_loaded`` and ``_decode_batch`` touch a real model and are marked
``# pragma: no cover`` in the source. The chat-template formatting and the public
``generate`` / ``generate_many`` plumbing are pure logic and are tested here by
injecting a fake tokenizer and stubbing the single model-bound method.
"""

from __future__ import annotations

from typing import Any

from groundlens.providers.hf import HFTextGenerator


def test_constructor_records_config() -> None:
    gen = HFTextGenerator("Qwen/Qwen2.5-7B-Instruct", seed=3, max_new_tokens=32)
    assert gen.model_name == "Qwen/Qwen2.5-7B-Instruct"
    assert gen.seed == 3
    assert gen.max_new_tokens == 32
    assert gen._model is None  # nothing loaded on construction


class _Tok:
    def apply_chat_template(self, messages: Any, **kwargs: Any) -> str:
        return f"<T>{messages[0]['content']}"


class _TokNoThinking:
    """Older tokenizer: rejects ``enable_thinking`` -> forces the TypeError fallback."""

    def apply_chat_template(
        self, messages: Any, tokenize: bool = False, add_generation_prompt: bool = True
    ) -> str:
        return f"<T2>{messages[0]['content']}"


def test_template_uses_tokenizer() -> None:
    gen = HFTextGenerator("m")
    gen._tok = _Tok()
    assert gen._template("hello") == "<T>hello"


def test_template_falls_back_when_enable_thinking_unsupported() -> None:
    gen = HFTextGenerator("m")
    gen._tok = _TokNoThinking()
    assert gen._template("hello") == "<T2>hello"


def _fake_decode(prompts: list[str], num_return_sequences: int) -> list[list[str]]:
    """Stand in for the model-bound ``_decode_batch``; keeps public plumbing real."""
    return [[f"{p}#{j}" for j in range(num_return_sequences)] for p in prompts]


def test_generate_returns_first_rows_completions() -> None:
    gen = HFTextGenerator("m")
    gen._decode_batch = _fake_decode  # type: ignore[method-assign]
    assert gen.generate("p", 3) == ["p#0", "p#1", "p#2"]


def test_generate_many_takes_one_per_prompt_and_chunks() -> None:
    gen = HFTextGenerator("m", batch_sequences=1)  # force multiple chunks
    gen._decode_batch = _fake_decode  # type: ignore[method-assign]
    assert gen.generate_many(["a", "b", "c"]) == ["a#0", "b#0", "c#0"]
