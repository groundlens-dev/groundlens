# Active-learning bootstrap (`DGI.propose_labels`)

This guide walks through using `DGI.propose_labels()` to bootstrap a verified-grounded calibration set for a new deployment. It is the practical step that turns "I don't have labelled data" into "I have 20 labelled pairs ready for `DGI.calibrate()`."

## When to use this

You should reach for `propose_labels` when:

- You are deploying groundlens in a new domain (banking, legal, healthcare, internal IT, etc.) and the bundled cross-domain `mu_hat` is not specific enough.
- You have a small seed of verified-grounded pairs (10–50) and want to grow the calibration set deliberately rather than by random sampling.
- You want the confabulated examples in your evaluation set to cover the failure modes embedding-based detectors actually miss, not the easy ones.

You should NOT use it for:

- SGI. SGI is a geometric ratio with no calibration parameter. `propose_labels` is a method on `DGI`, not `SGI`.
- Auto-labelling. The method does NOT label and does NOT calibrate. A human reviewer assigns the labels.
- Replacing real production data. The synthetic candidates are starting fuel for the calibration set; over time you should mix in verified-grounded pairs from your actual traffic.

## Anti-circularity by design

A natural worry: "If I use DGI to score the candidates and then use those scored candidates to calibrate DGI, isn't that circular?" Two things keep the loop honest:

1. **DGI orders the candidates; the human assigns the labels.** The acquisition function (uncertainty + diversity) picks which candidates the reviewer sees, but the `grounded` / `fabricated` decision is made by the human, not by the model. The same human-supplied labels are what go into `DGI.calibrate()`.
2. **The confabulations come from a separate generation step.** `llm_generate` is a callable you provide — typically OpenAI, Anthropic, or a local model. groundlens does not embed an LLM. The candidates are generated under explicit confabulation strategies that target the failure modes embedding models miss, so the labelling task is informative rather than padded with trivial negatives.

A second guardrail: **two reviewers labelling the same batch independently, then reconciling disagreements**. This is the most defensible practice for a regulated deployment. The Markdown checklist in `PropositionBatch.review_template` is designed to be copied directly into a shared review document.

## The five confabulation strategies

The default `strategies="default"` argument selects all five strategies from the human-confabulation taxonomy in [`groundlens-dev/grounding-benchmark`](https://github.com/groundlens-dev/grounding-benchmark) (CC BY 4.0). Each strategy preserves a different subset of the distributional properties that embedding models encode while violating referential truth.

| Strategy | What it does | Why it matters for DGI |
|---|---|---|
| `redefinition` | Redefines a key term in the grounded response while keeping vocabulary and register identical. | Targets cosine-similarity detectors: the embeddings look right, the facts are wrong. |
| `mechanism_inversion` | Reverses the underlying causal direction while preserving local sentence transitions. | Each sub-clause sounds plausible in isolation; only the global meaning is wrong. |
| `entity_composition` | Combines real institutions / procedures / agencies into a fictitious mechanism. | Every entity is real; the composition is invented. Hard for entity-based checks. |
| `polysemy` | Picks a word with multiple senses and shifts the response to the wrong sense, with consistent supporting context. | Tests whether DGI distinguishes sense disambiguation, not just topical proximity. |
| `template_filling` | Preserves the discourse structure (introduction, claim, justification, qualifier) while replacing every concrete fact with a plausible-but-wrong substitute. | Models the "right-shaped, wrong-fact" failure mode common in FAQ-RAG. |

Custom strategies are supported via `(name, prompt_template)` tuples; templates take the slots `{context}`, `{question}`, `{grounded}`.

## Minimal example

```python
from groundlens import DGI

def my_llm(prompt: str) -> str:
    # any OpenAI / Anthropic / local LLM wrapper you already use
    ...

dgi = DGI()  # starts from the bundled cross-domain calibration

seed_pairs = [
    ("What is the Bizum daily limit?",
     "The Bizum daily limit is 1,000 EUR per transaction and 2,000 EUR per day."),
    ("How do I increase my credit card limit?",
     "Request a credit-line increase from the app under Cards → Limit, subject to a credit review."),
    # ... 10-50 verified-grounded pairs total
]

batch = dgi.propose_labels(
    faq_corpus=public_faqs,           # list[str], the deployment's FAQ paragraphs
    seed_pairs=seed_pairs,
    llm_generate=my_llm,
    n_candidates=200,
    n_to_label=20,
    strategies="default",
    seed=42,                          # determinism is required for audits
)

# Hand the Markdown checklist to a human reviewer (or two).
print(batch.review_template)

# After review, feed the labelled grounded subset back to calibrate:
reviewer_grounded = [
    (q, r) for (q, r, label) in reviewed_items if label == "grounded"
]
dgi.calibrate(pairs=reviewer_grounded)
```

The `seed=42` argument is not cosmetic — passing the same `seed`, `faq_corpus`, and `seed_pairs` produces an identical batch. This is required for reproducible audits.

## What `PropositionBatch` returns

| Field | Type | Use |
|---|---|---|
| `items` | `tuple[ProposedLabel, ...]` | Top-ranked candidates for human review. Length ≤ `n_to_label`. |
| `review_template` | `str` | Markdown checklist with `[ ] grounded / [ ] fabricated / [ ] out_of_scope` per item, ready to copy into your review document. |
| `all_candidates` | `tuple[ProposedLabel, ...]` | Every candidate generated in the round, ordered by acquisition score. Useful for audit. |
| `strategies_used` | `tuple[str, ...]` | The strategy names actually used. |

Each `ProposedLabel` carries `question`, `candidate_response`, `dgi_score`, `strategy`, `context_excerpt`, and `uncertainty`. All fields are immutable (frozen dataclass).

## Acquisition function

The default mixes two signals:

- **Uncertainty (70%)** — the candidates with the smallest distance to the decision threshold. These are the candidates the current model finds hardest to classify, so a label on them shifts `mu_hat` the most.
- **Diversity (30%)** — remaining slots are filled with candidates from strategies under-represented in the uncertainty subset, ensuring all strategies surface in the batch.

The threshold is the **median DGI score on the seed grounded pairs** — a reasonable proxy for the grounded/ungrounded boundary when no calibrated threshold is available yet. You can change the uncertainty/diversity mix with `diverse_fraction`:

```python
batch = dgi.propose_labels(..., diverse_fraction=0.5)  # 50% uncertainty / 50% diversity
```

## Error handling

| Situation | What groundlens does |
|---|---|
| `seed_pairs=[]` | `ValueError` immediately. |
| `n_candidates < 1` | `ValueError` immediately. |
| `llm_generate` not callable | `TypeError` immediately. |
| `llm_generate` raises an exception | The failed candidate is skipped, a `RuntimeWarning` is emitted with the exception type and message, and the round continues. |
| `llm_generate` returns empty / whitespace | The candidate is silently skipped. |

These choices keep the loop resilient to flaky LLM endpoints without hiding systematic failures from the operator.

## Recommended workflow

1. **Seed.** Hand-curate 10–50 verified-grounded pairs from your domain. If you have nothing, start by writing them yourself from the FAQ corpus — even 10 pairs is enough to bootstrap.
2. **Round 1.** Call `propose_labels(n_candidates=200, n_to_label=20)`. Two reviewers label the batch independently, reconcile.
3. **Calibrate.** Pass the reconciled grounded subset to `DGI.calibrate(pairs=…)`. Threshold via `np.percentile(scores, 20)` (or your operational percentile).
4. **Round 2.** Call `propose_labels` again with the new `mu_hat` baked in. The uncertainty signal is now sharper, so the batch surfaces harder cases.
5. **Stop when AUROC plateaus.** Hold out a labelled evaluation set and stop adding pairs when AUROC on the held-out set stops improving for two consecutive rounds.
6. **Recalibrate on drift.** When DGI score distribution on production traffic shifts beyond a tolerance you set, run `propose_labels` again on the recent traffic as `faq_corpus`.

## References

- Marin, J. (2026). *A Methodology for Building Human-Confabulated Hallucination Benchmarks*. [`groundlens-dev/grounding-benchmark`](https://github.com/groundlens-dev/grounding-benchmark). CC BY 4.0.
- Marin, J. (2026). *A Geometric Taxonomy of Hallucinations in LLMs*. arXiv:2602.13224v3.

## See also

- [Domain calibration](domain-calibration.md) — what to do with the labelled pairs once you have them.
- [Banking deployment](banking-deployment.md) — full deployment pattern including audit log and compliance mapping.
- [Custom rule sets](custom-rule-sets.md) — the rules side of the triage layer.
