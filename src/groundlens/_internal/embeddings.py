"""Embedding model management with lazy loading and process-level caching.

The embedding model is the most expensive resource in groundlens. This module
ensures it is loaded exactly once per process and reused across all scoring
calls. The model is loaded lazily on first use — importing groundlens does
not trigger a download or GPU allocation.

Supported models (any sentence-transformers model works):
    - ``Snowflake/snowflake-arctic-embed-l-v2.0`` (default): 1024 dims, 568M
      params, multilingual (100+ languages), 8192 token context window.
      Snowflake's flagship retrieval encoder. Slightly heavier than smaller
      defaults but produces materially better grounding signal across SGI/DGI
      benchmarks (verified on RAGTruth + RAGBench, see CHANGELOG 2026.6.18).
    - ``all-MiniLM-L6-v2`` (legacy default through 2026.6.17): 384 dims,
      22M params, fast English-only. Available for lightweight deployments.
    - ``all-mpnet-base-v2``: 768 dims, 109M params, higher quality English.
    - ``MULTILINGUAL_MINI`` / ``MULTILINGUAL_E5``: see constants below.
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

DEFAULT_MODEL: str = "Snowflake/snowflake-arctic-embed-l-v2.0"
"""Default sentence transformer model.

Snowflake Arctic Embed L v2.0 — 1024 dims, 568M params, multilingual
(100+ languages including Spanish/Catalan/Galician/English/Portuguese),
8192 token context window. Requires ``trust_remote_code=True`` on load
(the model ships custom pooling code).

Why this is the default:

  - Verified on RAGTruth (n=2,700) and RAGBench (n=8,838) with consistent
    SGI/DGI behavior; calibrations in cookbooks ship against this encoder.
  - L2-normalizes embeddings naturally (contrastive training), which keeps
    the canonical angular SGI formulation numerically stable.
  - Multilingual out-of-the-box — relevant for European bank deployments.

When to override:

  - Lightweight deployment (CPU-only, latency-critical): use
    ``LIGHTWEIGHT_MINILM = "all-MiniLM-L6-v2"`` (22M params, 384 dims).
    The previous default through 2026.6.17.
  - Spanish/multilingual smaller footprint: use ``MULTILINGUAL_MINI``
    (118M params, 384 dims).
  - Higher quality multilingual at higher cost: use ``MULTILINGUAL_E5``
    (560M params, 1024 dims) with required "query: "/"passage: " prefixes.

To override globally, pass ``model="..."`` to ``compute_sgi``,
``compute_dgi``, or the corresponding scorer classes.
"""

LIGHTWEIGHT_MINILM: str = "all-MiniLM-L6-v2"
"""Lightweight English-only encoder (22M params, 384 dims). Was the default
through groundlens 2026.6.17. Use for latency-critical CPU-only deployments
where the trade-off in grounding signal quality is acceptable."""

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
