"""Slow, opt-in: the NLI scorer must reproduce SelfCheckGPT-NLI on WikiBio-GPT3.

This locks the baseline so the second-stage scorer cannot drift. It downloads
DeBERTa-v3-large-MNLI and the released dataset, so it is marked slow and skips
automatically when torch/transformers/datasets are absent. Run explicitly with::

    pytest tests/verify/test_wikibio_repro.py -m slow

Expected: SelfCheck-NLI AUC-PR (non-factual) near 92.5 (Manakul et al., EMNLP 2023).
"""

from __future__ import annotations

import pytest

pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("datasets")
pytest.importorskip("sklearn")

pytestmark = pytest.mark.slow


def test_selfcheck_nli_reproduces_wikibio_aucpr() -> None:
    import numpy as np
    from datasets import load_dataset
    from sklearn.metrics import average_precision_score

    from groundlens.verify.scorers import NLIScorer

    ds = load_dataset("potsawee/wiki_bio_gpt3_hallucination", split="evaluation")
    scorer = NLIScorer()
    nonfact = {"minor_inaccurate", "major_inaccurate"}
    scores: list[float] = []
    labels: list[int] = []
    for ex in ds:
        sents = ex["gpt3_sentences"]
        samples = ex["gpt3_text_samples"]
        if not sents or not samples:
            continue
        for sent, ann in zip(sents, ex["annotation"], strict=False):
            # premise=sentence, hypothesis=sample, mean P(contradiction) over samples
            prem = [sent] * len(samples)
            inc = float(np.mean(scorer._contradiction(prem, list(samples))))
            scores.append(inc)
            labels.append(1 if ann in nonfact else 0)
    aucpr = 100.0 * average_precision_score(labels, scores)
    assert aucpr > 90.0, f"AUC-PR {aucpr:.2f} is far from the paper's 92.5"
