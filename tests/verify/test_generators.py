"""API generators for the second stage, tested with stub clients (no SDK calls)."""

from __future__ import annotations

from typing import Any

from groundlens.verify import AnthropicGenerator, GeminiGenerator, OpenAIGenerator


class _AnthropicBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _AnthropicMsg:
    def __init__(self, text: str) -> None:
        self.content = [_AnthropicBlock(text)]


class _AnthropicClient:
    def __init__(self) -> None:
        self.calls = 0
        self.messages = self

    def create(self, **kwargs: Any) -> _AnthropicMsg:
        self.calls += 1
        return _AnthropicMsg(f"claude#{self.calls}")


def test_anthropic_generate_and_many() -> None:
    g = AnthropicGenerator(client=_AnthropicClient())
    assert g.generate("hi", 3) == ["claude#1", "claude#2", "claude#3"]
    assert g.generate_many(["a", "b"]) == ["claude#4", "claude#5"]


class _Choice:
    def __init__(self, text: str) -> None:
        self.message = type("M", (), {"content": text})()


class _OpenAIResp:
    def __init__(self, texts: list[str]) -> None:
        self.choices = [_Choice(t) for t in texts]


class _OpenAIClient:
    def __init__(self) -> None:
        self.chat = type("C", (), {"completions": self})()
        self.n_seen: list[int] = []

    def create(self, **kwargs: Any) -> _OpenAIResp:
        n = kwargs.get("n", 1)
        self.n_seen.append(n)
        return _OpenAIResp([f"gpt#{i}" for i in range(n)])


def test_openai_generate_uses_n_and_many_maps() -> None:
    client = _OpenAIClient()
    g = OpenAIGenerator(client=client)
    assert g.generate("hi", 3) == ["gpt#0", "gpt#1", "gpt#2"]
    assert client.n_seen[-1] == 3  # a single call with n=3
    assert g.generate_many(["a", "b"]) == ["gpt#0", "gpt#0"]


class _GeminiModel:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, prompt: str, **kwargs: Any) -> Any:
        self.calls += 1
        return type("R", (), {"text": f"gemini#{self.calls}"})()


def test_gemini_generate_and_many() -> None:
    g = GeminiGenerator(client=_GeminiModel())
    assert g.generate("hi", 2) == ["gemini#1", "gemini#2"]
    assert g.generate_many(["a", "b"]) == ["gemini#3", "gemini#4"]


def test_generators_satisfy_textgenerator_protocol() -> None:
    from groundlens.verify._base import TextGenerator

    for gen in (
        AnthropicGenerator(client=_AnthropicClient()),
        OpenAIGenerator(client=_OpenAIClient()),
        GeminiGenerator(client=_GeminiModel()),
    ):
        assert isinstance(gen, TextGenerator)


def test_generator_plugs_into_sample_consistency() -> None:
    # An API generator drives the second stage end to end (embedding scorer, no NLI model).
    from groundlens.verify import SampleConsistency

    sc = SampleConsistency(
        generator=AnthropicGenerator(client=_AnthropicClient()), scorer="embedding"
    )
    assert sc._generator is not None
