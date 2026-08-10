"""The reference encoder. Behind the ``[encoder]`` extra, imported lazily.

Nothing here is imported unless you construct a
:class:`SentenceTransformerEncoder`, so ``import groundlens`` never pulls torch.

The one thing to notice: the model is pinned by **revision sha**, not by name.
A silent re-upload of a checkpoint on the Hub would otherwise change every
number anyone ever published with this library, with no diff and no warning.
The resolved sha goes into ``Encoder.id`` and from there into
``profile_sha256``.
"""

from __future__ import annotations

from typing import Any

from groundlens._types import Span, WindowEncoding

DEFAULT_MODEL = "sentence-transformers/all-mpnet-base-v2"

_MISSING = (
    "The reference encoder needs the optional dependencies.\n"
    "    pip install 'groundlens[encoder]'\n"
    "The core library has none on purpose; only scoring text needs a model."
)


def _resolve_revision(model: str, revision: str | None) -> str:
    if revision:
        return revision
    try:
        from huggingface_hub import HfApi

        sha = HfApi().model_info(model).sha
    except Exception:
        return "unresolved"
    return str(sha) if sha else "unresolved"


def _to_host_array(vectors: Any) -> Any:
    """Bring whatever the model returned onto the host as a numpy array.

    ``SentenceTransformer.encode`` honours ``convert_to_numpy`` for sentence
    embeddings but not always for ``output_value="token_embeddings"`` -- several
    versions return a live torch tensor regardless. On CPU that is harmless
    because numpy can read it; on MPS or CUDA the memory is not on the host and
    ``np.asarray`` raises. Moving it explicitly is the only thing that works
    across accelerators, and it costs nothing when the input is already an array.

    Duck-typed on purpose: torch is not imported here, and any array-like that
    can reach the host is accepted.
    """
    import numpy as np

    detach = getattr(vectors, "detach", None)
    if callable(detach):
        vectors = detach()
    to_cpu = getattr(vectors, "cpu", None)
    if callable(to_cpu):
        vectors = to_cpu()
    to_numpy = getattr(vectors, "numpy", None)
    if callable(to_numpy):
        vectors = to_numpy()
    return np.asarray(vectors, dtype=np.float32)


class SentenceTransformerEncoder:
    """A frozen off-the-shelf sentence encoder, used one window at a time.

    Args:
        model: any sentence-transformers model id.
        revision: pin it explicitly. If omitted the sha is resolved from the Hub
            once, at construction. If that fails the id records ``"unresolved"``
            rather than pretending -- an unresolved id in a published hash is a
            visible defect, which is the point.
        device: passed straight through. ``None`` lets the library decide.
        max_tokens: overrides the model's own sequence limit. Leave it alone.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        revision: str | None = None,
        device: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise ImportError(_MISSING) from exc

        self._model_name = model
        self._revision = _resolve_revision(model, revision)
        kwargs: dict[str, Any] = {"device": device}
        if revision:
            kwargs["revision"] = revision
        self._model = SentenceTransformer(model, **{k: v for k, v in kwargs.items() if v})
        self._tokenizer = self._model.tokenizer
        limit = max_tokens or int(getattr(self._model, "max_seq_length", 384) or 384)
        # Two slots reserved for [CLS] and [SEP]; the window planner works in
        # content tokens and must not hand the model something it will truncate.
        self._max_tokens = max(1, limit - 2)

    @property
    def id(self) -> str:
        return f"{self._model_name.split('/')[-1]}@{self._revision}"

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def token_spans(self, text: str) -> tuple[Span, ...]:
        encoded = self._tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        return tuple((int(a), int(b)) for a, b in encoded["offset_mapping"] if int(b) > int(a))

    def encode_window(self, text: str) -> WindowEncoding:
        encoded = self._tokenizer(text, add_special_tokens=True, return_offsets_mapping=True)
        offsets = encoded["offset_mapping"]
        word_ids = encoded.word_ids()
        # Moved to the host BEFORE any indexing: on MPS and CUDA the returned
        # tensor cannot be read by numpy where it lives.
        vectors = _to_host_array(
            self._model.encode(text, output_value="token_embeddings", show_progress_bar=False)
        )

        keep: list[int] = []
        keep_spans: list[Span] = []
        keep_words: list[int | None] = []
        for index, (a, b) in enumerate(offsets):
            if index >= len(vectors) or int(b) <= int(a):
                # Special tokens carry no characters and must not become anchors.
                continue
            keep.append(index)
            keep_spans.append((int(a), int(b)))
            keep_words.append(word_ids[index] if word_ids else None)

        import numpy as np

        if keep:
            matrix = vectors[keep]
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            values = (matrix / np.maximum(norms, 1e-12)).tolist()
        else:
            values = []

        return WindowEncoding(
            token_spans=tuple(keep_spans),
            word_ids=tuple(keep_words),
            vectors=values,
        )
