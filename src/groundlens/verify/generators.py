"""API-backed text generators for the model-based second stage.

These adapters let the consistency checks (resample / reword) sample from a
hosted API instead of a local Hugging Face model. Each implements the
:class:`~groundlens.verify.TextGenerator` protocol (``generate`` /
``generate_many``), so it drops straight into ``SampleConsistency``,
``SelfCheckNLI``, ``ParaphraseCheck`` or :func:`~groundlens.verify.two_stage`
via ``generator=``.

The provider SDK is imported lazily, so importing this module needs no provider
package. Install the matching optional extra to use one:

    pip install "groundlens[anthropic]"   # AnthropicGenerator  (Claude)
    pip install "groundlens[openai]"      # OpenAIGenerator     (GPT + OpenAI-compatible)
    pip install "groundlens[google]"      # GeminiGenerator     (Gemini)

Sampling is always on (``temperature`` > 0): the second stage measures
disagreement across samples, so deterministic decoding would defeat it.

Data handling: your prompts and the model's answers are sent to the provider you
choose, under that provider's data terms, using YOUR API key. Groundlens holds
no key of its own and has no server in the path; it neither stores nor forwards
your data anywhere else. For a no-egress option, use the local
:class:`~groundlens.providers.hf.HFTextGenerator` instead. See ``DATA_HANDLING.md``.
"""

from __future__ import annotations

from typing import Any

_INSTALL = {
    "anthropic": 'pip install "groundlens[anthropic]"',
    "openai": 'pip install "groundlens[openai]"',
    "google": 'pip install "groundlens[google]"',
}


class AnthropicGenerator:
    """Sample from an Anthropic Claude model via the Anthropic SDK."""

    def __init__(
        self,
        model: str = "claude-3-5-haiku-latest",
        *,
        api_key: str | None = None,
        client: Any = None,
        max_tokens: int = 64,
        temperature: float = 0.7,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._api_key = api_key
        self._client = client

    def _ensure(self) -> Any:
        if self._client is None:  # pragma: no cover - builds a real SDK client; needs the extra
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - exercised only without the extra
                raise ImportError(_INSTALL["anthropic"]) from exc
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _one(self, prompt: str) -> str:
        msg = self._ensure().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", "text") == "text"]
        return "".join(parts).strip()

    def generate(self, prompt: str, n: int = 1) -> list[str]:
        """Return ``n`` sampled completions of a single prompt."""
        return [self._one(prompt) for _ in range(n)]

    def generate_many(self, prompts: list[str]) -> list[str]:
        """Return one sampled completion for each of ``prompts``."""
        return [self._one(p) for p in prompts]


class OpenAIGenerator:
    """Sample from an OpenAI model, or any OpenAI-compatible endpoint.

    Pass ``base_url`` to target a compatible server (e.g. DeepSeek, vLLM,
    Together, a local gateway); the rest of the interface is identical.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any = None,
        max_tokens: int = 64,
        temperature: float = 0.7,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._api_key = api_key
        self._base_url = base_url
        self._client = client

    def _ensure(self) -> Any:
        if self._client is None:  # pragma: no cover - builds a real SDK client; needs the extra
            try:
                import openai
            except ImportError as exc:  # pragma: no cover - exercised only without the extra
                raise ImportError(_INSTALL["openai"]) from exc
            self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def generate(self, prompt: str, n: int = 1) -> list[str]:
        """Return ``n`` sampled completions of a single prompt (one API call)."""
        resp = self._ensure().chat.completions.create(
            model=self.model,
            n=n,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return [(c.message.content or "").strip() for c in resp.choices]

    def generate_many(self, prompts: list[str]) -> list[str]:
        """Return one sampled completion for each of ``prompts``."""
        return [self.generate(p, 1)[0] for p in prompts]


class GeminiGenerator:
    """Sample from a Google Gemini model via the google-generativeai SDK."""

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        *,
        api_key: str | None = None,
        client: Any = None,
        max_output_tokens: int = 64,
        temperature: float = 0.7,
    ) -> None:
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self._api_key = api_key
        self._model_obj = client

    def _ensure(self) -> Any:
        if self._model_obj is None:  # pragma: no cover - builds a real SDK client; needs the extra
            try:
                import google.generativeai as genai
            except ImportError as exc:  # pragma: no cover - exercised only without the extra
                raise ImportError(_INSTALL["google"]) from exc
            if self._api_key:
                genai.configure(api_key=self._api_key)
            self._model_obj = genai.GenerativeModel(self.model)
        return self._model_obj

    def _one(self, prompt: str) -> str:
        resp = self._ensure().generate_content(
            prompt,
            generation_config={
                "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens,
            },
        )
        # resp.text is a property that raises ValueError when the candidate is
        # blocked or has no text part; treat that as an empty sample.
        try:
            text = resp.text
        except (ValueError, AttributeError):
            text = ""
        return (text or "").strip()

    def generate(self, prompt: str, n: int = 1) -> list[str]:
        """Return ``n`` sampled completions of a single prompt."""
        return [self._one(prompt) for _ in range(n)]

    def generate_many(self, prompts: list[str]) -> list[str]:
        """Return one sampled completion for each of ``prompts``."""
        return [self._one(p) for p in prompts]
