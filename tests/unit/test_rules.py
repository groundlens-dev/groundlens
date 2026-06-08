"""Unit tests for groundlens.rules."""

from __future__ import annotations

import pytest

from groundlens.rules import (
    ChecklistRule,
    RuleEvidence,
    RuleResult,
    RuleSet,
    RuleSetResult,
    banking_rules,
)


class TestBankingRulesetBasics:
    """Basic structural checks on the bundled banking ruleset."""

    def test_banking_ruleset_has_expected_name(self):
        rs = banking_rules()
        assert rs.name == "banking_v1"

    def test_banking_ruleset_has_22_rules(self):
        # 8 spec + 8 expl + 6 bshift
        rs = banking_rules()
        assert len(rs.rules) == 22

    def test_banking_ruleset_covers_three_sub_scores(self):
        rs = banking_rules()
        sub_scores = {r.sub_score for r in rs.rules}
        assert sub_scores == {"spec", "expl", "bshift"}

    def test_banking_ruleset_quality_floor_is_03(self):
        rs = banking_rules()
        assert rs.quality_floor == pytest.approx(0.3)

    def test_banking_ruleset_quality_floor_overridable(self):
        rs = banking_rules(quality_floor=0.5)
        assert rs.quality_floor == pytest.approx(0.5)


class TestEvaluateVacuousRationale:
    """A rationale that cites no specifics should be flagged."""

    def test_vacuous_rationale_flagged(self):
        rs = banking_rules()
        result = rs.evaluate(
            question="What governance decision?",
            response="Further review needed due to the complexity of the situation.",
        )
        assert result.flagged is True

    def test_vacuous_rationale_quality_collapses_to_zero(self):
        rs = banking_rules()
        result = rs.evaluate(
            question="What governance decision?",
            response="The case requires additional review.",
        )
        # No bshift match -> geometric mean collapses
        assert result.quality == pytest.approx(0.0)


class TestEvaluateMechanicalRationale:
    """A mechanical-template rationale should pass with high scores."""

    def test_mechanical_rationale_passes(self):
        rs = banking_rules()
        response = (
            "Hard gate K0_10 triggered: because information completeness (0.225) "
            "falls below threshold 0.3, the system is unable to confirm transaction "
            "legitimacy. Specifically, additional documentation is needed to raise "
            "completeness above 0.3. A favorable resolution would be possible if "
            "completeness exceeds 0.3."
        )
        result = rs.evaluate(
            question="What governance decision?",
            response=response,
            metadata={"flags_present": ["AML"]},
        )
        assert result.flagged is False
        assert result.spec > 0.5
        assert result.expl > 0.4
        assert result.bshift > 0.3
        assert result.quality > 0.0


class TestDeterminism:
    """Same inputs must always produce same outputs — CLAUDE.md constraint #1."""

    def test_same_inputs_same_output(self):
        rs = banking_rules()
        q = "What governance decision applies?"
        r = "Risk score 0.456 with AML flag triggers conditional review."
        r1 = rs.evaluate(question=q, response=r)
        r2 = rs.evaluate(question=q, response=r)
        assert r1.spec == r2.spec
        assert r1.expl == r2.expl
        assert r1.bshift == r2.bshift
        assert r1.quality == r2.quality
        assert r1.flagged == r2.flagged
        assert r1.audit_explanation == r2.audit_explanation


class TestAuditExplanation:
    """The audit explanation must surface rule ids, weights, and evidence."""

    def test_audit_explanation_lists_ruleset_name(self):
        rs = banking_rules()
        result = rs.evaluate(question="Q", response="risk score 0.456 mentioned here.")
        assert "Ruleset: banking_v1" in result.audit_explanation

    def test_audit_explanation_lists_verdict(self):
        rs = banking_rules()
        result = rs.evaluate(question="Q", response="risk score 0.456.")
        assert "Verdict:" in result.audit_explanation

    def test_audit_explanation_includes_matched_evidence(self):
        rs = banking_rules()
        result = rs.evaluate(question="Q", response="risk score 0.456 mentioned.")
        assert "0.456" in result.audit_explanation or "risk" in result.audit_explanation


class TestRuleResults:
    """Per-rule results should be accessible for downstream inspection."""

    def test_all_rules_produce_results(self):
        rs = banking_rules()
        result = rs.evaluate(question="Q", response="risk score 0.456.")
        assert len(result.rule_results) == len(rs.rules)

    def test_rule_result_carries_id_and_sub_score(self):
        rs = banking_rules()
        result = rs.evaluate(question="Q", response="risk score 0.456.")
        first = result.rule_results[0]
        assert first.rule_id != ""
        assert first.sub_score in {"spec", "expl", "bshift"}


class TestCustomRuleSet:
    """User-defined rule sets must work with the same evaluation contract."""

    def test_user_can_build_minimal_ruleset(self):
        def always_match(q, r, ctx, meta):
            return RuleEvidence(matched=True, span="x", explanation="always matches")

        rule = ChecklistRule(
            id="custom.always",
            description="always true",
            weight=0.5,
            sub_score="spec",
            check=always_match,
        )
        rs = RuleSet(name="custom", rules=(rule,))
        result = rs.evaluate(question="Q", response="anything goes here.")
        assert result.spec == pytest.approx(0.5)
        # expl/bshift have no rules → 0 → quality collapses
        assert result.quality == pytest.approx(0.0)
        assert result.flagged is True  # expl < 0.3


class TestEmptyResponseRejected:
    """An empty response must raise — auditing nothing is meaningless."""

    def test_empty_response_raises(self):
        rs = banking_rules()
        with pytest.raises(ValueError, match="non-empty"):
            rs.evaluate(question="Q", response="")

    def test_whitespace_response_raises(self):
        rs = banking_rules()
        with pytest.raises(ValueError, match="non-empty"):
            rs.evaluate(question="Q", response="   \n  ")


class TestFrozenDataclasses:
    """Result dataclasses must be immutable — CLAUDE.md constraint #3."""

    def test_ruleset_result_is_immutable(self):
        rs = banking_rules()
        result = rs.evaluate(question="Q", response="risk score 0.456.")
        with pytest.raises((AttributeError, Exception)):
            result.spec = 999  # type: ignore[misc]

    def test_rule_result_is_immutable(self):
        rs = banking_rules()
        result = rs.evaluate(question="Q", response="risk score 0.456.")
        with pytest.raises((AttributeError, Exception)):
            result.rule_results[0].matched = True  # type: ignore[misc]


class TestSubScoresAreCapped:
    """Sub-scores must not exceed 1.0 even if rule weights sum above 1."""

    def test_sub_scores_capped_at_one(self):
        rs = banking_rules()
        # Response that matches many spec rules
        rich = (
            "Risk score 0.456, AML flag present, K0_12 gate evaluated. "
            "Specifically, the completeness 0.225 indicates information gap. "
            "Transaction amount $850,000, jurisdiction ES, counterparty risk 0.388. "
            "In particular, the documentation completeness is insufficient."
        )
        result = rs.evaluate(question="Q", response=rich, metadata={"flags_present": ["AML"]})
        assert result.spec <= 1.0
        assert result.expl <= 1.0
        assert result.bshift <= 1.0
