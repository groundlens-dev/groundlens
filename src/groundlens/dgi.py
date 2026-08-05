"""Directional Grounding Index (DGI) — context-free grounding score.

DGI evaluates whether an LLM response follows the characteristic semantic
displacement pattern of grounded responses — without requiring source context.
It needs only a question and a response, plus calibration data.

Mathematical formulation:

    delta = phi(response) - phi(question)
    DGI = dot(delta / ||delta||, mu_hat)

where mu_hat is the mean direction of displacement vectors computed from
verified grounded (question, response) pairs. The DGI value captures the
*direction* of the displacement; its *magnitude* ``||delta||`` (how far the
response moved from the question) is returned separately on
``DGIResult.magnitude``.

Geometric interpretation:

    - DGI >= 0.525: aligns with the grounded reference direction (ok).
    - DGI < 0.525: diverges from grounded patterns (risk).

    DGI is a SINGLE binary cut, not a three-band scheme: ``compute_dgi``
    computes ``flagged = value < DGI_PASS`` and nothing else. The cut is the
    Youden's-J operating point on the bundled 212-pair reference set with the
    default sentence-t5-large encoder (AUROC 0.78 global; the local variant
    ``k=...`` separates best nearer 0.545). It is encoder- and domain-specific:
    recalibrate with ``fit_thresholds`` / ``DGI.calibrate``. The canonical
    value lives in :data:`groundlens._internal.thresholds.DGI_PASS` — read it
    from there rather than copying the number.

Calibration and ceiling:

    DGI's reference direction mu_hat is fit on verified grounded pairs.
    Calibration sets the operating point. It does not remove the blind spot.

    DGI's skill declines toward chance as a confabulation stays in the
    register of a correct answer. With authorship held constant it reaches
    AUROC 0.606, and the ceiling of the whole embedding-similarity class is
    about 0.68. That is a ceiling, not a shortfall: no decoder over these
    embeddings does materially better without reading authorship.

    Escalate in-register cases to a second stage: an entailment check (NLI),
    a source lookup, or a judge. Entailment does not decline in register.

Use cases:

    - Chat/dialogue verification (no retrieval context available).
    - Agent self-verification before returning results.
    - Batch evaluation of LLM outputs at scale.

References:
    Marin (2026). *A Geometric Taxonomy of Hallucinations in LLMs*.
    arXiv:2602.13224v3.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import numpy as np

from groundlens._internal.csv_loader import load_reference_pairs
from groundlens._internal.embeddings import (
    DEFAULT_MODEL,
    encode_texts,
    get_default_encoder,
)
from groundlens._internal.geometry import displacement_vector, unit_normalize
from groundlens._internal.thresholds import (
    DGI_PASS,
    _warn_default_thresholds_with_custom_encoder,
    normalize_dgi,
)
from groundlens.score import DGIResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

    from groundlens._internal.embeddings import EmbeddingFn
    from groundlens.propose import PropositionBatch, SeedExample

logger = logging.getLogger(__name__)

# ── Module-level reference direction cache ───────────────────────────────────

_mu_hat_cache: dict[tuple[str, str, int | None], NDArray[np.float32]] = {}
# Reference bank (unit query embeddings + unit grounded displacements) for the
# local variant Gamma_k. Keyed like the global cache.
_bank_cache: dict[
    tuple[str, str, int | None], tuple[NDArray[np.float32], NDArray[np.float32]]
] = {}


def _active_encoder_id(encoder: EmbeddingFn | None) -> int | None:
    """Identity of the encoder that ``encode_texts`` will actually use.

    ``encode_texts`` resolves an explicit ``encoder`` first and falls back to
    the process-global one set by :func:`groundlens.set_default_encoder`. Every
    cache key must be derived the same way, or a direction written under one
    key is looked up under another. That is exactly what used to break
    ``DGI.calibrate(pairs=...)`` under ``set_default_encoder``: ``calibrate``
    keyed on ``self.encoder`` (``None``) while ``_get_mu_hat`` keyed on the
    active global encoder, so ``score()`` raised "inline calibration not
    initialized" for a scorer that had just been calibrated.
    """
    active = encoder if encoder is not None else get_default_encoder()
    return id(active) if active is not None else None


def _compute_reference_direction(
    pairs: list[tuple[str, str]],
    model_name: str = DEFAULT_MODEL,
    *,
    encoder: EmbeddingFn | None = None,
) -> NDArray[np.float32]:
    """Compute the mean grounded displacement direction (mu_hat).

    Given N verified (question, response) pairs, compute:

        1. Embed all questions and responses.
        2. For each pair, compute delta_i = phi(r_i) - phi(q_i).
        3. Normalize each delta_i to unit length.
        4. Average the unit vectors and re-normalize.

    The result mu_hat is the maximum-likelihood estimate of the mean
    direction of a von Mises-Fisher distribution on S^(n-1).

    Args:
        pairs: List of (question, response) string tuples.
        model_name: Sentence transformer model.
        encoder: Optional bring-your-own-embeddings callable. When set,
            sentence-transformers is bypassed (no torch required).

    Returns:
        Unit-normalized mean direction vector, shape ``(d,)``.
    """
    texts: list[str] = []
    for q, r in pairs:
        texts.extend([q, r])

    embeddings = encode_texts(texts, model_name=model_name, encoder=encoder)

    displacements: list[NDArray[np.float32]] = []
    for i in range(len(pairs)):
        q_emb = embeddings[i * 2]
        r_emb = embeddings[i * 2 + 1]
        delta = displacement_vector(q_emb, r_emb)
        if float(np.linalg.norm(delta)) > 1e-8:
            displacements.append(unit_normalize(delta))

    if not displacements:
        msg = "No valid displacement vectors computed from reference pairs."
        raise ValueError(msg)

    # np.mean promotes to float64; cast back to the float32 embedding dtype.
    mu: NDArray[np.float32] = np.mean(np.stack(displacements), axis=0).astype(np.float32)
    return unit_normalize(mu)


def _get_reference_bank(
    model_name: str = DEFAULT_MODEL,
    reference_csv: str | None = None,
    *,
    encoder: EmbeddingFn | None = None,
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Embed and cache the reference set for the local variant Gamma_k.

    Returns ``(Q, D)``: ``Q`` are unit-normalized reference query embeddings
    (for nearest-neighbour selection) and ``D`` the matching unit-normalized
    grounded displacements. Cached like the global direction.
    """
    key = (
        model_name,
        reference_csv or "__bundled__",
        _active_encoder_id(encoder),
    )
    if key not in _bank_cache:
        if reference_csv == "__inline__":
            msg = (
                "The local DGI variant (k=...) needs a reference set. Pass "
                "reference_csv=... or use the bundled default; it is not "
                "available from DGI.calibrate(pairs=...)."
            )
            raise RuntimeError(msg)
        pairs = load_reference_pairs(reference_csv)
        texts: list[str] = []
        for q, r in pairs:
            texts.extend([q, r])
        emb = encode_texts(texts, model_name=model_name, encoder=encoder)
        q_list: list[NDArray[np.float32]] = []
        d_list: list[NDArray[np.float32]] = []
        for i in range(len(pairs)):
            q_emb, r_emb = emb[i * 2], emb[i * 2 + 1]
            delta = displacement_vector(q_emb, r_emb)
            if float(np.linalg.norm(delta)) > 1e-8:
                q_list.append(unit_normalize(q_emb))
                d_list.append(unit_normalize(delta))
        if not d_list:
            msg = "No valid reference displacements for the local DGI variant."
            raise ValueError(msg)
        _bank_cache[key] = (
            np.stack(q_list).astype(np.float32),
            np.stack(d_list).astype(np.float32),
        )
    return _bank_cache[key]


def _local_mu_hat(
    query_emb: NDArray[np.float32],
    bank: tuple[NDArray[np.float32], NDArray[np.float32]],
    k: int,
) -> NDArray[np.float32]:
    """Query-specific grounding direction from the k nearest reference queries."""
    q_ref, d_ref = bank
    k = max(1, min(int(k), q_ref.shape[0]))
    q_unit = unit_normalize(query_emb)
    sims = q_ref @ q_unit
    top = np.argpartition(-sims, k - 1)[:k]
    mu = d_ref[top].mean(axis=0).astype(np.float32)
    return unit_normalize(mu)


#: Filename of the precomputed reference direction that ships with the package.
#:
#: ``mu_hat`` is a pure function of the reference CSV and the encoder, so it was
#: derived from scratch on first use in every process: 424 texts through
#: sentence-t5-large, measured at 7m43s on a CI runner. That cost was paid by
#: CI on every run, by every user on their first DGI call, and by the demo Space
#: on every cold start -- to recompute a value that had not changed since it was
#: fitted.
#:
#: The vector ships instead, 3 KB. What it does not do is replace the check:
#: ``tests/integration/test_frozen_mu_hat.py`` derives it fresh with the real
#: encoder and asserts the shipped array matches. The derivation is still
#: proven, once, in the one place built to pay for it.
_FROZEN_MU_HAT = "mu_hat_sentence-t5-large.npy"
_FROZEN_META = "mu_hat_sentence-t5-large.json"


def _load_frozen_mu_hat(
    model_name: str,
    reference_csv: str | None,
    encoder: EmbeddingFn | None,
) -> NDArray[np.float32] | None:
    """The shipped reference direction, or ``None`` if it does not apply here.

    Returns ``None`` -- falling back to deriving from the CSV -- unless every
    one of these holds:

    * the bundled reference set is in use (no ``reference_csv``),
    * the default encoder is in use (no explicit ``encoder``, no process-global
      one from :func:`groundlens.set_default_encoder`, and ``model_name`` is
      :data:`DEFAULT_MODEL`),
    * the file is present, is one unit vector of the recorded width,
    * and the SHA-256 recorded for ``reference_pairs.csv`` matches the CSV that
      is actually installed.

    That last condition is the one that matters. A frozen vector is a claim
    about a CSV; edit the CSV without regenerating and the claim is false. The
    hash makes that case fall back to deriving rather than silently scoring
    against a direction fitted on data no longer in the package.
    """
    if reference_csv is not None or model_name != DEFAULT_MODEL:
        return None
    if encoder is not None or get_default_encoder() is not None:
        return None

    try:
        import hashlib
        import json
        from importlib.resources import files

        data = files("groundlens.data")
        meta = json.loads((data / _FROZEN_META).read_text(encoding="utf-8"))

        digest = hashlib.sha256((data / "reference_pairs.csv").read_bytes()).hexdigest()
        if digest != meta["reference_pairs_sha256"]:
            logger.warning(
                "Bundled reference_pairs.csv does not match the precomputed DGI "
                "direction (expected sha256 %s, found %s). Deriving from the CSV. "
                "Regenerate with: python -m groundlens.tools.freeze_mu_hat",
                meta["reference_pairs_sha256"][:12],
                digest[:12],
            )
            return None

        with (data / _FROZEN_MU_HAT).open("rb") as fh:
            mu = np.load(fh, allow_pickle=False).astype(np.float32)
    except Exception as exc:  # any failure to read the artifact means derive instead
        logger.warning("Could not load the precomputed DGI direction (%s). Deriving.", exc)
        return None

    if mu.ndim != 1 or mu.shape[0] != meta["dims"]:
        logger.warning("Precomputed DGI direction has shape %s; deriving instead.", mu.shape)
        return None
    if not np.isclose(float(np.linalg.norm(mu)), 1.0, atol=1e-5):
        logger.warning("Precomputed DGI direction is not a unit vector; deriving instead.")
        return None

    logger.debug("Using the precomputed DGI reference direction (%s).", _FROZEN_MU_HAT)
    return mu


def _get_mu_hat(
    model_name: str = DEFAULT_MODEL,
    reference_csv: str | None = None,
    *,
    encoder: EmbeddingFn | None = None,
) -> NDArray[np.float32]:
    """Get the cached reference direction, computing on first access.

    Caches by ``(model_name, reference_csv, encoder identity)`` key. Using
    different CSV paths or a custom encoder produces independent reference
    directions, so a custom encoder never reuses a stale bundled mu_hat.

    Args:
        model_name: Sentence transformer model.
        reference_csv: Path to user CSV, or ``None`` for bundled data.
        encoder: Optional bring-your-own-embeddings callable. Its identity
            is folded into the cache key.

    Returns:
        Unit-normalized reference direction, shape ``(d,)``.
    """
    # A process-global encoder (set_default_encoder) is a hidden second input
    # to encode_texts; fold it in so the certified vector is never dotted against
    # a foreign embedding space and the cache never returns a stale direction.
    cache_key = (
        model_name,
        reference_csv or "__bundled__",
        _active_encoder_id(encoder),
    )

    if cache_key not in _mu_hat_cache:
        # The inline sentinel only resolves via cache; there is no on-disk
        # CSV to fall back to. Surface a clear error rather than letting
        # load_reference_pairs raise FileNotFoundError on a sentinel string.
        if reference_csv == "__inline__":
            msg = (
                "DGI inline calibration not initialized. Call "
                "DGI.calibrate(pairs=...) on a DGI instance before scoring."
            )
            raise RuntimeError(msg)
        # Compute the reference direction from the bundled reference set (or a
        # user CSV) in the active encoder's own space, so it always reproduces
        # from the shipped data. First use embeds the set, then caches.
        logger.info(
            "Resolving DGI reference direction (model=%s, data=%s)...",
            model_name,
            reference_csv or "bundled",
        )
        frozen = _load_frozen_mu_hat(model_name, reference_csv, encoder)
        if frozen is not None:
            _mu_hat_cache[cache_key] = frozen
            logger.info(
                "DGI reference direction loaded from package data (dims=%d).",
                frozen.shape[0],
            )
        else:
            pairs = load_reference_pairs(reference_csv)
            _mu_hat_cache[cache_key] = _compute_reference_direction(
                pairs, model_name, encoder=encoder
            )
            logger.info(
                "DGI reference direction ready (dims=%d, pairs=%d).",
                _mu_hat_cache[cache_key].shape[0],
                len(pairs),
            )

    return _mu_hat_cache[cache_key]


def compute_dgi(
    question: str,
    response: str,
    *,
    model: str = DEFAULT_MODEL,
    reference_csv: str | None = None,
    encoder: EmbeddingFn | None = None,
    k: int | None = None,
) -> DGIResult:
    """Compute the Directional Grounding Index for a response.

    Args:
        question: The input query.
        response: The LLM output to evaluate.
        model: Sentence transformer model name.
        reference_csv: Path to domain-specific calibration CSV.
            If ``None``, uses the bundled dataset.
        encoder: Optional bring-your-own-embeddings callable taking
            ``list[str]`` and returning an ``(n, d)`` array. Bypasses
            sentence-transformers (no torch required) when provided.
        k: If set, use the local variant Gamma_k: build the reference
            direction from the ``k`` reference queries nearest to ``question``,
            instead of one global mean direction. Needs the reference set (the
            bundled data or ``reference_csv``); the first local call embeds it.
            Clamped to ``[1, len(reference_set)]``, so ``k=0`` and negative
            values behave as ``k=1``.

    Returns:
        DGIResult with raw score, normalized score, and flag status.

    Raises:
        ValueError: If question or response is empty.

    Example:
        >>> from groundlens import compute_dgi
        >>> result = compute_dgi(
        ...     question="What causes seasons on Earth?",
        ...     response="Seasons are caused by Earth's 23.5-degree axial tilt.",
        ... )
        >>> result.flagged
        False
    """
    if not question.strip():
        msg = "question must be a non-empty string."
        raise ValueError(msg)
    if not response.strip():
        msg = "response must be a non-empty string."
        raise ValueError(msg)

    if reference_csv is None and (
        encoder is not None or model != DEFAULT_MODEL or get_default_encoder() is not None
    ):
        _warn_default_thresholds_with_custom_encoder("compute_dgi", model, encoder is not None)

    embeddings = encode_texts([question, response], model_name=model, encoder=encoder)
    q_emb, r_emb = embeddings[0], embeddings[1]

    # Global Gamma uses one mean direction; local Gamma_k uses a query-specific
    # direction from the k nearest reference queries (paper Eq. 4).
    if k is not None:
        mu_hat = _local_mu_hat(
            q_emb, _get_reference_bank(model, reference_csv, encoder=encoder), k
        )
    else:
        mu_hat = _get_mu_hat(model, reference_csv, encoder=encoder)

    delta = displacement_vector(q_emb, r_emb)
    magnitude = float(np.linalg.norm(delta))

    # Degenerate case: response identical to question.
    if magnitude < 1e-8:
        return DGIResult(value=0.0, normalized=0.0, flagged=True, magnitude=round(magnitude, 4))

    delta_hat = delta / magnitude
    gamma = float(np.dot(delta_hat, mu_hat))

    if math.isnan(gamma):
        logger.warning("DGI produced NaN — check embedding dimensions.")
        return DGIResult(value=0.0, normalized=0.0, flagged=True, magnitude=round(magnitude, 4))

    normalized = round(normalize_dgi(gamma), 4)

    return DGIResult(
        value=round(gamma, 4),
        normalized=normalized,
        flagged=gamma < DGI_PASS,
        magnitude=round(magnitude, 4),
    )


def reset_calibration_cache() -> None:
    """Clear all cached reference directions and banks. Useful for testing."""
    _mu_hat_cache.clear()
    _bank_cache.clear()


class DGI:
    """Reusable DGI scorer with pre-configured model and calibration.

    Use this class when evaluating multiple responses against the same
    reference direction. Supports both bundled and custom calibration.

    Example:
        >>> dgi = DGI()
        >>> result = dgi.score(
        ...     question="What is ML?",
        ...     response="ML is a branch of AI.",
        ... )
        >>> result.flagged
        False

        >>> dgi = DGI(reference_csv="my_domain_pairs.csv")
        >>> result = dgi.score(question="...", response="...")
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        reference_csv: str | None = None,
        encoder: EmbeddingFn | None = None,
        k: int | None = None,
    ) -> None:
        """Initialize DGI scorer.

        Args:
            model: Sentence transformer model name.
            reference_csv: Path to domain-specific calibration CSV.
            encoder: Optional bring-your-own-embeddings callable. When set,
                both calibration and scoring bypass sentence-transformers
                (no torch required).
            k: If set, score with the local variant Gamma_k (query-specific
                reference direction from the k nearest reference queries).
        """
        self.model = model
        self.reference_csv = reference_csv
        self.encoder = encoder
        self.k = k

    def calibrate(
        self,
        pairs: list[tuple[str, str]] | None = None,
        csv_path: str | None = None,
    ) -> None:
        """Set custom calibration data.

        Either provide pairs directly or a path to a CSV file.
        This replaces any previously cached reference direction.

        Args:
            pairs: List of verified (question, response) tuples.
            csv_path: Path to a calibration CSV file.

        Raises:
            ValueError: If neither ``pairs`` nor ``csv_path`` is provided.
        """
        enc_id = _active_encoder_id(self.encoder)

        if csv_path is not None:
            self.reference_csv = csv_path
            # Force recomputation on next score() call.
            cache_key = (self.model, csv_path, enc_id)
            _mu_hat_cache.pop(cache_key, None)
            return

        if pairs is not None:
            # Compute and cache the reference direction directly.
            mu = _compute_reference_direction(pairs, self.model, encoder=self.encoder)
            cache_key = (self.model, "__inline__", enc_id)
            _mu_hat_cache[cache_key] = mu
            self.reference_csv = "__inline__"
            return

        msg = "Provide either 'pairs' or 'csv_path' for calibration."
        raise ValueError(msg)

    def score(self, question: str, response: str) -> DGIResult:
        """Compute DGI for a single response.

        Args:
            question: The input query.
            response: The LLM output to evaluate.

        Returns:
            DGIResult with score and flag status.

        Raises:
            RuntimeError: If ``calibrate(pairs=...)`` has not been called
                yet on this instance and ``reference_csv`` is the inline
                sentinel.
        """
        if self.reference_csv == "__inline__":
            # Guard: the inline mu_hat must already be in the cache, since
            # there is no on-disk CSV to fall back to.
            enc_id = _active_encoder_id(self.encoder)
            cache_key = (self.model, "__inline__", enc_id)
            if cache_key not in _mu_hat_cache:
                msg = "Call calibrate() before score() when using inline pairs."
                raise RuntimeError(msg)

        # Pass reference_csv through unchanged. ``_get_mu_hat`` resolves:
        #   None         -> bundled mu_hat
        #   real path    -> load CSV, compute mu_hat
        #   "__inline__" -> hit the cache populated by calibrate(pairs=...)
        return compute_dgi(
            question=question,
            response=response,
            model=self.model,
            reference_csv=self.reference_csv,
            encoder=self.encoder,
            k=self.k,
        )

    def propose_labels(
        self,
        *,
        seeds: list[SeedExample],
        llm_generate: Callable[[str], str],
        n_candidates: int = 50,
        n_to_label: int = 10,
        strategies: str | tuple[str | tuple[str, str], ...] = "default",
        diverse_fraction: float = 0.3,
        seed: int = 42,
    ) -> PropositionBatch:
        """Active-learning bootstrap of a verified-grounded calibration set.

        Given 10-50 verified-grounded :class:`SeedExample` triples and a
        text-generation callable, this method:

        1. Picks a seed at random for each candidate and rewrites its
           ``grounded`` response under one of the named confabulation
           strategies, using the seed's own ``context`` as the source
           of truth in the prompt. Coherence is preserved by design --
           the prompt never sees a mismatched context+question pair.
        2. Scores each generated candidate with this DGI.
        3. Ranks candidates by acquisition score (70% uncertainty /
           30% strategy diversity) and returns the top ``n_to_label``
           for a human reviewer.

        The method DOES NOT label and DOES NOT calibrate. The human
        reviewer assigns the labels; the caller then passes the labelled
        grounded subset to :meth:`calibrate`. The loop is non-circular
        by design.

        Args:
            seeds: 10-50 verified-grounded :class:`SeedExample` triples.
                Each carries its own ``context``, ``question`` and
                ``grounded`` response, so the generation prompt is
                always coherent.
            llm_generate: A callable ``(prompt: str) -> str`` that the
                user provides (an OpenAI / Anthropic / local LLM
                wrapper). groundlens does not embed an LLM.
            n_candidates: Total candidates to generate across all
                strategies. Default 50 (≈5 minutes at 4 s/call).
            n_to_label: How many candidates the batch should contain.
                Default 10. The rest are returned in
                ``batch.all_candidates`` for audit.
            strategies: ``"default"`` (all five strategies from
                ``groundlens-dev/grounding-benchmark``), or a tuple of
                strategy names, or a tuple of ``(name, prompt_template)``
                custom pairs. Templates accept the slots ``{context}``,
                ``{question}``, ``{grounded}``.
            diverse_fraction: Fraction of the batch reserved for
                strategy diversity (the rest is filled by uncertainty).
                Default 0.3.
            seed: Random seed for sampling seeds across rounds.
                Determinism is required for reproducible audits.

        Returns:
            A :class:`groundlens.PropositionBatch` ready for human review.

        Raises:
            ValueError: If ``seeds`` is empty or ``n_candidates`` < 1.
            TypeError: If ``llm_generate`` is not callable, or any
                element of ``seeds`` is not a ``SeedExample``.
        """
        import random
        import warnings

        from groundlens._internal.strategies import resolve_strategies
        from groundlens.propose import (
            ProposedLabel,
            PropositionBatch,
            SeedExample,
            _uncertainty,
            build_review_template,
            rank_for_labelling,
        )

        if not seeds:
            msg = "seeds must contain at least one SeedExample."
            raise ValueError(msg)
        if not all(isinstance(s, SeedExample) for s in seeds):
            msg = (
                "Every item in seeds must be a SeedExample(context=..., "
                "question=..., grounded=...) instance."
            )
            raise TypeError(msg)
        if n_candidates < 1:
            msg = "n_candidates must be >= 1."
            raise ValueError(msg)
        if not callable(llm_generate):
            msg = "llm_generate must be a callable (prompt: str) -> str."
            raise TypeError(msg)

        resolved_strategies = resolve_strategies(strategies)
        if not resolved_strategies:
            msg = "At least one strategy must be specified."
            raise ValueError(msg)

        # Threshold: median DGI score on the seed grounded pairs. This is
        # a reasonable proxy for the boundary between grounded and
        # ungrounded when no calibrated threshold is available yet.
        seed_scores = [self.score(s.question, s.grounded).normalized for s in seeds]
        sorted_scores = sorted(seed_scores)
        n = len(sorted_scores)
        median = (
            sorted_scores[n // 2]
            if n % 2 == 1
            else 0.5 * (sorted_scores[n // 2 - 1] + sorted_scores[n // 2])
        )
        threshold = float(median)

        rng = random.Random(seed)

        # Round-robin across strategies. For each candidate, sample ONE
        # seed and pass its OWN (context, question, grounded) through
        # the strategy template. No more mismatched context/seed pairs.
        candidates: list[ProposedLabel] = []
        per_strategy = max(1, n_candidates // len(resolved_strategies))
        for strat_name, template in resolved_strategies:
            for _ in range(per_strategy):
                if len(candidates) >= n_candidates:
                    break
                anchor = rng.choice(seeds)
                prompt = template.format(
                    context=anchor.context,
                    question=anchor.question,
                    grounded=anchor.grounded,
                )
                try:
                    candidate_resp = llm_generate(prompt)
                except Exception as exc:
                    msg = (
                        f"llm_generate raised {type(exc).__name__}: {exc}. "
                        "Skipping this candidate."
                    )
                    warnings.warn(msg, RuntimeWarning, stacklevel=2)
                    continue

                if not isinstance(candidate_resp, str) or not candidate_resp.strip():
                    continue

                score = self.score(anchor.question, candidate_resp).normalized
                candidates.append(
                    ProposedLabel(
                        question=anchor.question,
                        candidate_response=candidate_resp.strip(),
                        dgi_score=float(score),
                        strategy=strat_name,
                        context_excerpt=anchor.context,
                        uncertainty=_uncertainty(float(score), threshold),
                    )
                )

        # Rank for labelling (uncertainty + diversity).
        ranked = rank_for_labelling(
            candidates,
            n_to_label=n_to_label,
            diverse_fraction=diverse_fraction,
        )

        # Audit: keep all candidates, ordered by uncertainty.
        all_ordered = sorted(candidates, key=lambda c: c.uncertainty)

        return PropositionBatch(
            items=tuple(ranked),
            review_template=build_review_template(ranked),
            all_candidates=tuple(all_ordered),
            strategies_used=tuple(name for name, _ in resolved_strategies),
        )
