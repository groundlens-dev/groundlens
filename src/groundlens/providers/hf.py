"""Local Hugging Face text generator for the model-based second stage.

This is deliberately *not* part of the deterministic core. It is imported only
by :mod:`groundlens.verify` and needs the optional ``[verify]`` extra::

    pip install "groundlens[verify]"

which pulls in ``transformers``, ``torch`` and ``accelerate``. Importing this
module does **not** import torch: the heavy imports happen lazily on the first
``generate`` call, so ``import groundlens.verify`` stays cheap and the
deterministic ``import groundlens`` path never touches a model.

Generation is batched. ``generate(prompt, n)`` draws ``n`` samples of a single
prompt in one call via ``num_return_sequences``; ``generate_many(prompts)``
draws one sample for each of many prompts in padded batches. Decoder-only
batching requires left padding, which is set here.
"""

from __future__ import annotations

from typing import Any

_INSTALL_HINT = (
    "The model-based second stage needs the optional extra: "
    'pip install "groundlens[verify]"  (transformers, torch, accelerate).'
)


class HFTextGenerator:
    """A lazily-loaded, batched local text generator around a HF causal LM.

    Any object exposing ``generate(prompt, n)`` and ``generate_many(prompts)``
    can stand in for this (see :class:`groundlens.verify.TextGenerator`), so the
    second stage is not tied to Hugging Face; this is the batteries-included
    local default.

    Args:
        model: HF model id, e.g. ``"Qwen/Qwen2.5-7B-Instruct"``.
        load_in_4bit: Load in 4-bit (needs ``bitsandbytes``); keeps a 7-14B model
            near ~8 GB so it fits a single mid-range GPU.
        max_new_tokens: Generation cap. Short-answer QA needs little.
        temperature, top_p: Sampling parameters (sampling is always on, since the
            second stage measures disagreement across samples).
        batch_sequences: Max sequences per underlying ``generate`` call; lower it
            if you hit out-of-memory, raise it on a large GPU.
        device_map: Passed through to ``from_pretrained`` (default ``"auto"``).
        trust_remote_code: Passed through to tokenizer and model loading.
        seed: Optional seed set before each generation for reproducibility.
    """

    def __init__(
        self,
        model: str,
        *,
        load_in_4bit: bool = True,
        max_new_tokens: int = 64,
        temperature: float = 0.7,
        top_p: float = 0.9,
        batch_sequences: int = 24,
        device_map: str = "auto",
        trust_remote_code: bool = True,
        seed: int | None = None,
    ) -> None:
        self.model_name = model
        self.load_in_4bit = load_in_4bit
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.batch_sequences = batch_sequences
        self.device_map = device_map
        self.trust_remote_code = trust_remote_code
        self.seed = seed
        self._tok: Any = None
        self._model: Any = None
        self._torch: Any = None

    # -- lazy loading -------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(_INSTALL_HINT) from exc

        tok = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=self.trust_remote_code
        )
        tok.padding_side = "left"  # decoder-only batching needs left padding
        if tok.pad_token_id is None:
            tok.pad_token = tok.eos_token

        kwargs: dict[str, Any] = {
            "torch_dtype": "auto",
            "device_map": self.device_map,
            "trust_remote_code": self.trust_remote_code,
        }
        if self.load_in_4bit:
            try:
                from transformers import BitsAndBytesConfig
            except ImportError as exc:  # pragma: no cover
                raise ImportError(_INSTALL_HINT) from exc
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16
            )
        self._model = AutoModelForCausalLM.from_pretrained(self.model_name, **kwargs).eval()
        self._tok = tok
        self._torch = torch

    def _template(self, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        try:
            return str(
                self._tok.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
                )
            )
        except TypeError:
            return str(
                self._tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            )

    def _decode_batch(self, prompts: list[str], num_return_sequences: int) -> list[list[str]]:
        self._ensure_loaded()
        torch = self._torch
        if self.seed is not None:
            torch.manual_seed(self.seed)
        texts = [self._template(p) for p in prompts]
        enc = self._tok(
            texts, return_tensors="pt", padding=True, truncation=True, max_length=1024
        ).to(self._model.device)
        with torch.no_grad():
            out = self._model.generate(
                **enc,
                max_new_tokens=self.max_new_tokens,
                do_sample=True,
                temperature=self.temperature,
                top_p=self.top_p,
                num_return_sequences=num_return_sequences,
                pad_token_id=self._tok.pad_token_id,
            )
        gen = out[:, enc.input_ids.shape[1] :]  # left padding => prompts end at the same column
        dec = self._tok.batch_decode(gen, skip_special_tokens=True)
        k = num_return_sequences
        return [[dec[i * k + j].strip() for j in range(k)] for i in range(len(prompts))]

    # -- public API ---------------------------------------------------------
    def generate(self, prompt: str, n: int = 1) -> list[str]:
        """Return ``n`` sampled completions of a single ``prompt`` (one batched call)."""
        return self._decode_batch([prompt], num_return_sequences=n)[0]

    def generate_many(self, prompts: list[str]) -> list[str]:
        """Return one sampled completion per prompt, batched to ``batch_sequences``."""
        out: list[str] = []
        step = max(1, self.batch_sequences)
        for start in range(0, len(prompts), step):
            chunk = prompts[start : start + step]
            out.extend(row[0] for row in self._decode_batch(chunk, num_return_sequences=1))
        return out
