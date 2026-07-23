"""Consistency scorers for the second stage.

- :class:`NLIScorer` is the validated SelfCheck-NLI measure: it reproduces the
  92.50 AUC-PR reported by Manakul et al. (EMNLP 2023) on the WikiBio-GPT3 set.
  Premise is the answer being checked, hypothesis is each sample, and the score
  is the mean probability of contradiction. It needs the ``[verify]`` extra
  (torch, transformers) and loads its model lazily.
- :class:`EmbeddingScorer` reuses Groundlens's own sentence encoder (a core
  dependency, no extra needed) and measures mean cosine disagreement. Cheaper and
  lighter, weaker than NLI.

Both return an inconsistency in ``[0.0, 1.0]``; higher means less self-consistent.
When no usable samples are available they return ``1.0`` (maximum inconsistency),
so the pipeline fails toward human review rather than silently passing.
"""

from __future__ import annotations

from typing import Any

_INSTALL_HINT = (
    "NLIScorer needs the optional extra: "
    'pip install "groundlens[verify]"  (transformers, torch). '
    "For a no-extra option use EmbeddingScorer."
)


def _statement(question: str, answer: str) -> str:
    """Turn a (question, answer) pair into a declarative statement for NLI."""
    return f"{question.strip().rstrip('?')}? {answer.strip()}"


class NLIScorer:
    """SelfCheck-NLI consistency via a DeBERTa-v3 MNLI model (validated, batched).

    Args:
        model: HF sequence-classification model id fine-tuned for NLI.
        device: ``"cuda"`` / ``"cpu"``; defaults to CUDA when available.
        max_length: Tokenizer truncation length for each pair.
        batch_size: Pairs per forward pass.
    """

    def __init__(
        self,
        model: str = "potsawee/deberta-v3-large-mnli",
        *,
        device: str | None = None,
        max_length: int = 256,
        batch_size: int = 32,
    ) -> None:
        self.model_name = model
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size
        self._tok: Any = None
        self._model: Any = None
        self._torch: Any = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(_INSTALL_HINT) from exc
        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._tok = AutoTokenizer.from_pretrained(self.model_name)
        self._model = (
            AutoModelForSequenceClassification.from_pretrained(self.model_name).to(device).eval()
        )
        self._torch = torch
        self.device = device

    def _contradiction(self, premises: list[str], hypotheses: list[str]) -> list[float]:
        self._ensure_loaded()
        torch = self._torch
        out: list[float] = []
        with torch.inference_mode():
            for start in range(0, len(premises), self.batch_size):
                prem = premises[start : start + self.batch_size]
                hyp = hypotheses[start : start + self.batch_size]
                enc = self._tok(
                    prem,
                    hyp,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                ).to(self.device)
                logits = self._model(**enc).logits
                probs = torch.softmax(logits, dim=-1)[:, 1]  # index 1 == contradiction
                out.extend(probs.float().cpu().tolist())
        return out

    def inconsistency(self, question: str, answer: str, samples: list[str]) -> float:
        """Mean P(contradiction) of the answer against each sample; ``1.0`` if none usable."""
        usable = [s for s in samples if s and s.strip()]
        if not (answer and answer.strip()) or not usable:
            return 1.0
        premises = [_statement(question, answer)] * len(usable)
        hypotheses = [_statement(question, s) for s in usable]
        scores = self._contradiction(premises, hypotheses)
        return float(sum(scores) / len(scores))


class EmbeddingScorer:
    """Consistency via mean cosine disagreement, using Groundlens's own encoder.

    Needs no optional extra: it reuses the sentence encoder that SGI/DGI use, so
    the second stage's embedding path runs on the core install.

    Args:
        encoder: Optional custom embedding function; defaults to Groundlens's
            configured encoder.
    """

    def __init__(self, encoder: Any = None) -> None:
        self._encoder = encoder

    def inconsistency(self, question: str, answer: str, samples: list[str]) -> float:
        """Mean cosine disagreement of the answer against each sample; ``1.0`` if none usable."""
        import numpy as np

        from groundlens._internal.embeddings import encode_texts

        usable = [s for s in samples if s and s.strip()]
        if not (answer and answer.strip()) or not usable:
            return 1.0
        vectors = encode_texts([answer, *usable], encoder=self._encoder)
        arr = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        arr = arr / np.clip(norms, 1e-12, None)
        main = arr[0]
        cosines = arr[1:] @ main
        return float(np.mean(1.0 - cosines))
