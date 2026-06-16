"""Embedding model management with lazy loading and process-level caching.

The embedding model is the most expensive resource in groundlens. This module
ensures it is loaded exactly once per process and reused across all scoring
calls. The model is loaded lazily on first use — importing groundlens does
not trigger a download or GPU allocation.

Supported models (any sentence-transformers model works):
    - ``all-MiniLM-L6-v2`` (default): 384 dims, 22M params, fast.
    - ``all-mpnet-base-v2``: 768 dims, 109M params, higher quality.
    - ``gte-small``: 384 dims, Alibaba DAMO, multilingual.
    - Any model on HuggingFace Hub compatible with sentence-transformers.

Thread safety:
    The global cache uses module-level state. In multi-threaded applications,
    the first thread to call ``get_encoder()`` initializes the model; subsequent
    threads reuse it. The ``SentenceTransformer.encode()`` method is thread-safe.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_MODEL: str = "all-MiniLM-L6-v2"
"""Default sentence transformer model. Fast and accurate for English."""

MULTILINGUAL_MINI: str = "paraphrase-multilingual-MiniLM-L12-v2"
"""Multilingual MiniLM (118M params, 384 dims, 50+ languages including
Spanish, Catalan, Galician, English). Sub-second on CPU. Recommended
default for European-bank customer-support deployments where the
WhatsApp / app channel receives queries across the bank's operating
languages. Calibrate ``mu_hat`` and SGI threshold on a multilingual
verified-grounded corpus for the expected query distribution."""

MULTILINGUAL_E5: str = "intfloat/multilingual-e5-large"
"""Multilingual E5 (560M params, 1024 dims, 100+ languages). Higher
quality than ``MULTILINGUAL_MINI`` at ~5x the inference cost. Choose
when latency budget allows it (e.g. batch evaluation, audit replay) and
the deployment domain has shown weak separation under MiniLM. Requires
prefixing queries with ``"query: "`` and passages with ``"passage: "``
to match the encoder's training recipe; see model card on HuggingFace."""

# ── Module-level cache ──────────��────────────────────────────────────────────

_encoder: SentenceTransformer | None = None
_encoder_model_name: str | None = None


def get_encoder(model_name: str = DEFAULT_MODEL) -> Any:
    """Load a sentence transformer model, caching for process lifetime.

    The model is downloaded on first use (cached to ``~/.cache/torch/``
    by sentence-transformers) and kept in memory for the duration of the
    process. Changing ``model_name`` between calls loads the new model
    and replaces the cache.

    Args:
        model_name: HuggingFace model name or local path. Must be
            compatible with the sentence-transformers library.

    Returns:
        A ``SentenceTransformer`` instance ready for ``.encode()``.

    Raises:
        ImportError: If ``sentence-transformers`` is not installed.
    """
    global _encoder, _encoder_model_name

    if _encoder is not None and _encoder_model_name == model_name:
        return _encoder

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        msg = (
            "sentence-transformers is required for groundlens scoring. "
            "Install with: pip install groundlens"
        )
        raise ImportError(msg) from exc

    logger.info("Loading embedding model: %s", model_name)
    _encoder = SentenceTransformer(model_name)
    _encoder_model_name = model_name
    logger.info("Embedding model loaded: %s", model_name)

    return _encoder


def encode_texts(
    texts: list[str],
    model_name: str = DEFAULT_MODEL,
) -> NDArray[np.float32]:
    """Encode a list of texts into embedding vectors.

    Args:
        texts: Strings to encode. Empty strings produce zero vectors.
        model_name: Sentence transformer model to use.

    Returns:
        Array of shape ``(len(texts), embedding_dim)`` with float32 values.
        Embeddings are NOT L2-normalized (raw encoder output).
    """
    encoder = get_encoder(model_name)
    embeddings: NDArray[np.float32] = encoder.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=False,
    )
    return embeddings


def reset_cache() -> None:
    """Clear the cached encoder. Useful for testing or memory management."""
    global _encoder, _encoder_model_name
    _encoder = None
    _encoder_model_name = None
