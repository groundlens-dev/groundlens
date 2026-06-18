"""Unit tests for ``DGI.propose_labels`` and the ``propose`` module.

These tests mock the embedding model and the LLM generator so the suite
runs in milliseconds without external dependencies.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from groundlens import DGI, ProposedLabel, PropositionBatch, SeedExample
from groundlens._internal.strategies import DEFAULT_STRATEGIES, resolve_strategies
from groundlens.propose import (
    _uncertainty,
    build_review_template,
    rank_for_labelling,
)

# ── Strategy resolution ──────────────────────────────────────────────


class TestResolveStrategies:
    def test_default_returns_all_five(self) -> None:
        resolved = resolve_strategies("default")
        names = [n for n, _ in resolved]
        assert tuple(names) == DEFAULT_STRATEGIES
        for _, template in resolved:
            assert "{context}" in template
            assert "{question}" in template
            assert "{grounded}" in template

    def test_subset_of_names(self) -> None:
        resolved = resolve_strategies(("redefinition", "polysemy"))
        assert [n for n, _ in resolved] == ["redefinition", "polysemy"]

    def test_single_strategy_name_as_string(self) -> None:
        resolved = resolve_strategies("redefinition")
        assert len(resolved) == 1
        assert resolved[0][0] == "redefinition"

    def test_custom_pair(self) -> None:
        custom = (("my_strategy", "ctx={context} q={question} g={grounded}"),)
        resolved = resolve_strategies(custom)
        assert resolved == custom

    def test_mixed_names_and_custom_pairs(self) -> None:
        mixed = (
            "redefinition",
            ("my_strategy", "ctx={context} q={question} g={grounded}"),
        )
        resolved = resolve_strategies(mixed)
        assert [n for n, _ in resolved] == ["redefinition", "my_strategy"]

    def test_unknown_strategy_raises(self) -> None:
        with pytest.raises(KeyError):
            resolve_strategies("not_a_real_strategy_xyz")

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(TypeError):
            resolve_strategies(123)  # type: ignore[arg-type]

    def test_invalid_entry_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid strategy entry"):
            resolve_strategies((("only_one_element",),))  # type: ignore[arg-type]


# ── Acquisition function ─────────────────────────────────────────────


def _label(strategy: str, dgi_score: float, threshold: float = 0.5) -> ProposedLabel:
    return ProposedLabel(
        question="q",
        candidate_response="r",
        dgi_score=dgi_score,
        strategy=strategy,
        context_excerpt="ctx",
        uncertainty=_uncertainty(dgi_score, threshold),
    )


class TestRankForLabelling:
    def test_zero_to_label_returns_empty(self) -> None:
        cands = [_label("a", 0.5)]
        assert rank_for_labelling(cands, n_to_label=0) == []

    def test_empty_candidates_returns_empty(self) -> None:
        assert rank_for_labelling([], n_to_label=5) == []

    def test_most_uncertain_first(self) -> None:
        # Threshold 0.5 -> 0.50 is most uncertain.
        cands = [
            _label("a", 0.10),
            _label("a", 0.50),
            _label("a", 0.90),
        ]
        ranked = rank_for_labelling(cands, n_to_label=3, diverse_fraction=0.0)
        assert [c.dgi_score for c in ranked] == [0.50, 0.10, 0.90] or [
            c.dgi_score for c in ranked
        ] == [0.50, 0.90, 0.10]

    def test_diversity_fills_unrepresented_strategies(self) -> None:
        # All most-uncertain are strategy "a"; diversity should pull in "b".
        cands = [
            _label("a", 0.50),
            _label("a", 0.49),
            _label("a", 0.48),
            _label("b", 0.30),  # less uncertain but new strategy
        ]
        ranked = rank_for_labelling(cands, n_to_label=4, diverse_fraction=0.25)
        strategies = {c.strategy for c in ranked}
        assert strategies == {"a", "b"}


# ── SeedExample validation ───────────────────────────────────────────


class TestSeedExample:
    def test_valid_seed(self) -> None:
        s = SeedExample(
            context="Bizum permite enviar dinero...",
            question="Cual es el limite?",
            grounded="1000 EUR por transaccion.",
        )
        assert s.context.startswith("Bizum")
        assert s.question.endswith("?")
        assert s.grounded.endswith(".")

    def test_seed_is_frozen(self) -> None:
        s = SeedExample(context="c", question="q", grounded="g")
        with pytest.raises(Exception):  # noqa: B017, PT011  (FrozenInstanceError)
            s.context = "other"  # type: ignore[misc]

    @pytest.mark.parametrize("field", ["context", "question", "grounded"])
    def test_empty_field_raises(self, field: str) -> None:
        kwargs = {"context": "c", "question": "q", "grounded": "g"}
        kwargs[field] = ""
        with pytest.raises(ValueError, match=f"SeedExample.{field}"):
            SeedExample(**kwargs)

    @pytest.mark.parametrize("field", ["context", "question", "grounded"])
    def test_whitespace_field_raises(self, field: str) -> None:
        kwargs = {"context": "c", "question": "q", "grounded": "g"}
        kwargs[field] = "   "
        with pytest.raises(ValueError, match=f"SeedExample.{field}"):
            SeedExample(**kwargs)


# ── DGI.propose_labels with mocked DGI.score ─────────────────────────


class _FakeDGIResult:
    def __init__(self, normalized: float) -> None:
        self.normalized = normalized
        self.flagged = normalized < 0.5


def _seed(context: str = "ctx", question: str = "q", grounded: str = "g") -> SeedExample:
    return SeedExample(context=context, question=question, grounded=grounded)


class TestProposeLabels:
    """Exercise DGI.propose_labels with a stubbed score() method.

    score() is monkey-patched so the test runs without loading a
    sentence-transformer model. The stub returns a deterministic score
    derived from the candidate response length, which is enough to
    exercise ranking, diversity, error paths, and strategy plumbing.
    """

    def _make_dgi(self, monkeypatch: pytest.MonkeyPatch) -> DGI:
        dgi = DGI()

        def fake_score(question: str, response: str) -> _FakeDGIResult:
            # Score = clamped (len(response) % 100) / 100, so different
            # responses get different scores.
            value = (len(response) % 100) / 100.0
            return _FakeDGIResult(normalized=value)

        monkeypatch.setattr(dgi, "score", fake_score)
        return dgi

    def test_returns_propositionbatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dgi = self._make_dgi(monkeypatch)
        calls = []

        def fake_llm(prompt: str) -> str:
            calls.append(prompt)
            return f"resp_{len(calls)}"

        batch = dgi.propose_labels(
            seeds=[
                _seed("FAQ one.", "q1", "a1"),
                _seed("FAQ two.", "q2", "a2"),
            ],
            llm_generate=fake_llm,
            n_candidates=10,
            n_to_label=4,
            strategies="default",
            seed=0,
        )

        assert isinstance(batch, PropositionBatch)
        assert len(batch.items) <= 4
        assert all(isinstance(it, ProposedLabel) for it in batch.items)
        assert batch.strategies_used == DEFAULT_STRATEGIES
        # Review template references all items.
        assert "Human review batch" in batch.review_template
        for i in range(1, len(batch.items) + 1):
            assert f"Item {i}/{len(batch.items)}" in batch.review_template

    def test_prompt_receives_matched_context_and_seed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The bug fixed in 2026.6.17: context and seed must come from the
        SAME SeedExample, never randomly paired."""
        dgi = self._make_dgi(monkeypatch)
        captured_prompts: list[str] = []

        def capture_llm(prompt: str) -> str:
            captured_prompts.append(prompt)
            return "x"

        seeds = [
            _seed("CONTEXT_BIZUM", "Q_BIZUM", "G_BIZUM"),
            _seed("CONTEXT_HIPOTECA", "Q_HIPOTECA", "G_HIPOTECA"),
        ]

        dgi.propose_labels(
            seeds=seeds,
            llm_generate=capture_llm,
            n_candidates=10,
            n_to_label=2,
            strategies=("redefinition",),
            seed=0,
        )

        # Every prompt must carry context+question+grounded from the SAME seed.
        for prompt in captured_prompts:
            if "CONTEXT_BIZUM" in prompt:
                assert "Q_BIZUM" in prompt
                assert "G_BIZUM" in prompt
                assert "Q_HIPOTECA" not in prompt
                assert "G_HIPOTECA" not in prompt
            elif "CONTEXT_HIPOTECA" in prompt:
                assert "Q_HIPOTECA" in prompt
                assert "G_HIPOTECA" in prompt
                assert "Q_BIZUM" not in prompt
                assert "G_BIZUM" not in prompt
            else:
                pytest.fail(f"prompt has neither context: {prompt[:120]}")

    def test_all_strategies_appear_with_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dgi = self._make_dgi(monkeypatch)

        def fake_llm(prompt: str) -> str:
            return "x" * (np.random.default_rng(42).integers(10, 90))

        batch = dgi.propose_labels(
            seeds=[_seed()],
            llm_generate=fake_llm,
            n_candidates=50,
            n_to_label=20,
            strategies="default",
            seed=0,
        )
        used = {c.strategy for c in batch.all_candidates}
        assert used == set(DEFAULT_STRATEGIES)

    def test_custom_strategies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dgi = self._make_dgi(monkeypatch)

        def fake_llm(prompt: str) -> str:
            return "fixed_response"

        batch = dgi.propose_labels(
            seeds=[_seed()],
            llm_generate=fake_llm,
            n_candidates=4,
            n_to_label=4,
            strategies=(
                ("custom_a", "A: {context} {question} {grounded}"),
                ("custom_b", "B: {context} {question} {grounded}"),
            ),
            seed=0,
        )
        assert set(batch.strategies_used) == {"custom_a", "custom_b"}

    def test_empty_seeds_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dgi = self._make_dgi(monkeypatch)
        with pytest.raises(ValueError, match="seeds"):
            dgi.propose_labels(
                seeds=[],
                llm_generate=lambda p: "r",
                n_candidates=5,
            )

    def test_non_seed_item_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dgi = self._make_dgi(monkeypatch)
        with pytest.raises(TypeError, match="SeedExample"):
            dgi.propose_labels(
                seeds=[("q", "g")],  # type: ignore[list-item]
                llm_generate=lambda p: "r",
                n_candidates=5,
            )

    def test_n_candidates_below_one_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dgi = self._make_dgi(monkeypatch)
        with pytest.raises(ValueError, match="n_candidates"):
            dgi.propose_labels(
                seeds=[_seed()],
                llm_generate=lambda p: "r",
                n_candidates=0,
            )

    def test_non_callable_llm_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dgi = self._make_dgi(monkeypatch)
        with pytest.raises(TypeError, match="callable"):
            dgi.propose_labels(
                seeds=[_seed()],
                llm_generate="not_a_function",  # type: ignore[arg-type]
                n_candidates=5,
            )

    def test_llm_exception_skips_candidate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dgi = self._make_dgi(monkeypatch)
        n_calls = {"count": 0}

        def flaky_llm(prompt: str) -> str:
            n_calls["count"] += 1
            if n_calls["count"] % 2 == 0:
                raise RuntimeError("simulated LLM failure")
            return f"ok_{n_calls['count']}"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            batch = dgi.propose_labels(
                seeds=[_seed()],
                llm_generate=flaky_llm,
                n_candidates=10,
                n_to_label=10,
                strategies=("redefinition",),
                seed=0,
            )
        # At least one RuntimeWarning surfaced.
        assert any(issubclass(w.category, RuntimeWarning) for w in caught), (
            "expected RuntimeWarning on flaky LLM"
        )
        # And we still got SOME candidates back.
        assert len(batch.items) > 0

    def test_llm_returning_empty_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dgi = self._make_dgi(monkeypatch)

        def empty_llm(prompt: str) -> str:
            return "   "

        batch = dgi.propose_labels(
            seeds=[_seed()],
            llm_generate=empty_llm,
            n_candidates=5,
            n_to_label=5,
            strategies=("redefinition",),
            seed=0,
        )
        assert len(batch.items) == 0
        assert len(batch.all_candidates) == 0


# ── Review template ──────────────────────────────────────────────────


class TestReviewTemplate:
    def test_renders_each_item(self) -> None:
        items = [
            ProposedLabel(
                question="What is X?",
                candidate_response="X is a fictional concept.",
                dgi_score=0.23,
                strategy="redefinition",
                context_excerpt="From FAQ: X is defined as ...",
                uncertainty=0.10,
            ),
            ProposedLabel(
                question="What is Y?",
                candidate_response="Y is a category of Z.",
                dgi_score=-0.12,
                strategy="polysemy",
                context_excerpt="From FAQ: Y is ...",
                uncertainty=0.05,
            ),
        ]
        out = build_review_template(items)
        assert "Item 1/2" in out
        assert "Item 2/2" in out
        assert "redefinition" in out
        assert "polysemy" in out
        assert "[ ] grounded" in out
        assert "[ ] fabricated" in out
