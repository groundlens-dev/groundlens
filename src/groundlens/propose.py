"""Active-learning helper for bootstrapping a DGI calibration dataset.

A new deployment needs a verified-grounded corpus before
:func:`groundlens.compute_dgi` can produce meaningful scores. Curating
that corpus from scratch is the practical bottleneck most teams hit
first. This module implements the *propose* half of an
active-learning loop: given a list of self-contained
``SeedExample(context, question, grounded)`` triples and a text-generation
callable, it produces a ranked batch of candidate ``(question, response)``
pairs for a human reviewer to label.

The loop is intentionally non-circular: the DGI score *orders* the
candidates by uncertainty, but the *label* is supplied by the human at
the end. Calibration on the labelled batch then sharpens the same DGI
that proposed the next batch.

Public types
------------

- :class:`SeedExample` -- one verified-grounded triple
  ``(context, question, grounded)`` you supply as input.
- :class:`ProposedLabel` -- one candidate ready for review.
- :class:`PropositionBatch` -- the batch returned by
  :meth:`groundlens.DGI.propose_labels`.

All three are exposed at the top of the package.

References:
----------
Marin, J. (2026). *A Methodology for Building Human-Confabulated
Hallucination Benchmarks*. groundlens-dev/grounding-benchmark.
CC BY 4.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeedExample:
    """One verified-grounded triple you supply to ``DGI.propose_labels``.

    A ``SeedExample`` binds a FAQ paragraph (``context``) to a question
    that paragraph answers (``question``) and the verified-grounded
    response to that question (``grounded``). Bundling the three
    together is what keeps the candidate generation coherent: the
    confabulation prompt receives the *same* context, question and
    grounded answer rather than randomly-paired pieces.

    Attributes:
        context: A paragraph from the deployment's FAQ corpus that
            supports the grounded response.
        question: A question whose answer is contained in ``context``.
        grounded: The verified-grounded response to ``question`` given
            ``context``. The confabulation strategies rewrite this
            response under specific failure modes.

    Raises:
        ValueError: If any field is empty or whitespace-only.
    """

    context: str
    question: str
    grounded: str

    def __post_init__(self) -> None:
        """Validate that every field is a non-empty, non-whitespace string."""
        for name in ("context", "question", "grounded"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                msg = f"SeedExample.{name} must be a non-empty string."
                raise ValueError(msg)


@dataclass(frozen=True)
class ProposedLabel:
    """One candidate (question, response) pair ready for human review.

    Attributes:
        question: A question grounded in one of the FAQ-corpus entries.
        candidate_response: A confabulated response written by the
            generation LLM under the named ``strategy``.
        dgi_score: The DGI normalized score of the candidate against
            the current ``mu_hat``. Lower scores mean stronger
            deferral signal.
        strategy: The name of the confabulation strategy that produced
            this candidate (e.g. ``"redefinition"``).
        context_excerpt: The FAQ excerpt the question was anchored to.
        uncertainty: Distance of ``dgi_score`` from the threshold used
            for ranking. Smaller = more uncertain = higher priority.
    """

    question: str
    candidate_response: str
    dgi_score: float
    strategy: str
    context_excerpt: str
    uncertainty: float


@dataclass(frozen=True)
class PropositionBatch:
    """A batch of candidates returned by :meth:`groundlens.DGI.propose_labels`.

    Attributes:
        items: Candidates ordered by acquisition score (most useful to
            label first). Length up to ``n_to_label``.
        review_template: A Markdown template instructing the human
            reviewer how to label the items in the batch.
        all_candidates: Every candidate generated in the round, ordered
            by acquisition score. Useful for audit and debugging.
        strategies_used: The tuple of strategy names actually used.
    """

    items: tuple[ProposedLabel, ...]
    review_template: str
    all_candidates: tuple[ProposedLabel, ...] = field(default_factory=tuple)
    strategies_used: tuple[str, ...] = field(default_factory=tuple)


# ── Acquisition function ─────────────────────────────────────────────


def _uncertainty(score: float, threshold: float) -> float:
    """Acquisition: distance from the decision threshold.

    Lower = more uncertain = higher priority. The default threshold is
    the median DGI score of the seed set, which is a reasonable proxy
    for the boundary between grounded and ungrounded responses when no
    calibrated threshold is available yet.
    """
    return abs(score - threshold)


def rank_for_labelling(
    candidates: list[ProposedLabel],
    *,
    n_to_label: int,
    diverse_fraction: float = 0.3,
) -> list[ProposedLabel]:
    """Pick the ``n_to_label`` most useful candidates for a human reviewer.

    The default acquisition mixes two signals:

    - **Uncertainty (70%):** the ``ceil((1 - diverse_fraction) * n_to_label)``
      candidates with the smallest distance to the threshold. These are
      the candidates the current model finds hardest to classify, so a
      label on them shifts ``mu_hat`` the most.
    - **Diversity (30%):** the remaining slots are filled with
      candidates from strategies under-represented in the uncertainty
      subset, ensuring all strategies surface in the batch.

    Args:
        candidates: Candidates to rank. Each carries its own
            ``uncertainty`` score; smaller is more uncertain.
        n_to_label: How many candidates to return.
        diverse_fraction: Fraction of the batch reserved for diversity.
            ``0.3`` by default.

    Returns:
        List of selected candidates in ranked order.
    """
    if n_to_label <= 0:
        return []
    if not candidates:
        return []

    n_uncertain = max(1, round((1.0 - diverse_fraction) * n_to_label))
    n_diverse = max(0, n_to_label - n_uncertain)

    # 1) Uncertainty top-n.
    by_uncertainty = sorted(candidates, key=lambda c: c.uncertainty)
    uncertain_pick = by_uncertainty[:n_uncertain]

    # 2) Diversity: among the remaining candidates, prefer strategies
    #    NOT represented in `uncertain_pick`.
    used_strategies = {c.strategy for c in uncertain_pick}
    rest = list(by_uncertainty[n_uncertain:])
    rest.sort(
        key=lambda c: (
            0 if c.strategy not in used_strategies else 1,
            c.uncertainty,
        )
    )
    diverse_pick = rest[:n_diverse]

    return [*uncertain_pick, *diverse_pick]


# ── Review template ──────────────────────────────────────────────────


_REVIEW_TEMPLATE = """\
# Human review batch -- groundlens propose_labels

This batch contains **{n}** candidate (question, response) pairs proposed
by an active-learning loop. Each candidate was generated under a
specific confabulation strategy and scored against the current
DGI ``mu_hat``. Items are ordered with the most uncertain at the top
(the labels that will shift ``mu_hat`` the most when added to the
calibration set).

## Instructions

For each item below, decide one of:

- **grounded**: the response correctly answers the question given the
  context. Add the pair to your verified-grounded calibration set.
- **fabricated**: the response is wrong relative to the context. Do
  NOT add it to the calibration set; use it only for evaluation.
- **out_of_scope**: the question is not about the FAQ context, or the
  context is not sufficient. Discard.

Do not split your attention -- the value of active learning depends on
each label being deliberate. Two reviewers labelling the same batch
independently and reconciling disagreements is the most defensible
practice for a regulated deployment.

## Items

{items}
"""


_ITEM_TEMPLATE = """\
### Item {idx}/{total} -- strategy: `{strategy}`

**FAQ context excerpt:**

> {context_excerpt}

**Question:** {question}

**Candidate response:**

> {candidate_response}

**DGI score:** {dgi_score:+.3f}  |  **Uncertainty:** {uncertainty:.3f}

**Reviewer decision:** [ ] grounded  [ ] fabricated  [ ] out_of_scope

**Reviewer note (optional):** _______________________________________

---
"""


def build_review_template(items: list[ProposedLabel]) -> str:
    """Render the Markdown template for a batch of proposed labels."""
    body_parts = []
    for idx, it in enumerate(items, start=1):
        body_parts.append(
            _ITEM_TEMPLATE.format(
                idx=idx,
                total=len(items),
                strategy=it.strategy,
                context_excerpt=it.context_excerpt[:500],
                question=it.question,
                candidate_response=it.candidate_response[:1000],
                dgi_score=it.dgi_score,
                uncertainty=it.uncertainty,
            )
        )
    return _REVIEW_TEMPLATE.format(n=len(items), items="\n".join(body_parts))
