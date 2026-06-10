"""Tests for groundlens.agents — per-agent rule sets."""

from __future__ import annotations

import pytest

from groundlens.agents import rag_rules, routing_rules, specialized_agent_rules
from groundlens.rules import RuleSet

# ── routing_rules ────────────────────────────────────────────────────────────


class TestRoutingRules:
    def test_factory_returns_ruleset(self) -> None:
        rs = routing_rules()
        assert isinstance(rs, RuleSet)
        assert rs.name == "groundlens_routing_v1"
        assert len(rs.rules) == 10

    def test_sub_scores_cover_four_categories(self) -> None:
        rs = routing_rules()
        assert rs.sub_scores == (
            "intent_clarity",
            "classification_confidence",
            "fallback_appropriateness",
            "disambiguation_quality",
        )

    def test_every_rule_has_citation(self) -> None:
        rs = routing_rules()
        for rule in rs.rules:
            assert rule.citation, f"rule {rule.id} missing citation"
            assert len(rule.citation) >= 20

    def test_clean_single_intent_high_confidence_passes(self) -> None:
        rs = routing_rules()
        result = rs.evaluate(
            question="show my account balance",
            response="OK, fetching your balance now.",
            metadata={
                "predicted_intent": "show_balance",
                "top1_score": 0.92,
                "margin": 0.40,
                "allowed_intents": ["show_balance", "transfer", "open_account"],
                "fallback_fired": False,
                "query_in_scope": True,
            },
        )
        assert not result.flagged
        assert result.sub_scores["intent_clarity"] > 0.5
        assert result.sub_scores["classification_confidence"] > 0.5

    def test_multi_intent_query_flagged_on_intent_clarity(self) -> None:
        rs = routing_rules()
        result = rs.evaluate(
            question="transfer 500 EUR and then check my card balance",
            response="OK.",
            metadata={
                "predicted_intent": "transfer",
                "top1_score": 0.85,
                "margin": 0.30,
                "fallback_fired": False,
                "query_in_scope": True,
            },
        )
        rule_ids_failed = {r.rule_id for r in result.rule_results if not r.matched}
        assert "routing.single_intent_signal" in rule_ids_failed

    def test_low_confidence_triggers_flag(self) -> None:
        rs = routing_rules()
        result = rs.evaluate(
            question="open an account",
            response="Routing to open_account.",
            metadata={
                "predicted_intent": "open_account",
                "top1_score": 0.30,
                "margin": 0.05,
                "fallback_fired": False,
                "query_in_scope": True,
            },
        )
        assert result.flagged
        assert result.sub_scores["classification_confidence"] < 0.5

    def test_silent_fallback_flagged(self) -> None:
        rs = routing_rules()
        result = rs.evaluate(
            question="how do I solve climate change",
            response="...",
            metadata={
                "predicted_intent": "fallback",
                "top1_score": 0.10,
                "margin": 0.02,
                "fallback_fired": True,
                "query_in_scope": False,
            },
        )
        rule_ids_failed = {r.rule_id for r in result.rule_results if not r.matched}
        assert "routing.no_silent_fallback" in rule_ids_failed

    def test_low_margin_with_clarify_passes_disambiguation(self) -> None:
        rs = routing_rules()
        result = rs.evaluate(
            question="send money",
            response="Do you mean an internal transfer or a Bizum to a contact?",
            metadata={
                "predicted_intent": "transfer",
                "top1_score": 0.55,
                "margin": 0.05,
                "fallback_fired": False,
                "query_in_scope": True,
                "clarify_fired": True,
                "candidate_intents": ["internal_transfer", "bizum_transfer"],
            },
        )
        assert result.sub_scores["disambiguation_quality"] > 0.3

    def test_abstain_on_missing_metadata(self) -> None:
        rs = routing_rules()
        # No metadata at all — rules that depend on metadata abstain.
        result = rs.evaluate(
            question="show balance",
            response="OK.",
            metadata={},
        )
        # No top1_score, so confidence check abstains (matched=True by abstain).
        # Intent clarity should still pass.
        assert result.sub_scores["intent_clarity"] > 0.5


# ── specialized_agent_rules ──────────────────────────────────────────────────


class TestSpecializedAgentRules:
    def test_factory_returns_ruleset(self) -> None:
        rs = specialized_agent_rules()
        assert isinstance(rs, RuleSet)
        assert rs.name == "groundlens_specialized_v1"
        assert len(rs.rules) == 9

    def test_sub_scores_cover_four_categories(self) -> None:
        rs = specialized_agent_rules()
        assert rs.sub_scores == (
            "entity_groundedness",
            "entity_completeness",
            "entity_calibration",
            "execution_readiness",
        )

    def test_every_rule_has_citation(self) -> None:
        rs = specialized_agent_rules()
        for rule in rs.rules:
            assert rule.citation, f"rule {rule.id} missing citation"

    def test_clean_transfer_with_confirmation_passes(self) -> None:
        rs = specialized_agent_rules()
        # ES91 2100 0418 4502 0005 1332 — valid Spanish IBAN (passes mod 97)
        valid_iban = "ES9121000418450200051332"
        result = rs.evaluate(
            question="transfer 500 to ES91 2100 0418 4502 0005 1332",
            response=f"Transferring 500 EUR to {valid_iban}.",
            metadata={
                "dialog": (f"transfer 500 to {valid_iban}. yes confirm."),
                "entities": {"amount": 500, "iban": valid_iban},
                "required_entities": ["amount", "iban"],
                "confirmed": True,
                "operation": "wire_transfer",
            },
        )
        assert result.sub_scores["entity_groundedness"] > 0.9
        assert result.sub_scores["entity_completeness"] > 0.9
        assert result.sub_scores["execution_readiness"] > 0.7

    def test_hallucinated_iban_flagged(self) -> None:
        rs = specialized_agent_rules()
        # Captured IBAN does NOT appear in dialog
        hallucinated_iban = "ES8200810098000000000001"
        result = rs.evaluate(
            question="send 200 to my brother",
            response="Sending 200 EUR.",
            metadata={
                "dialog": "send 200 to my brother. yes confirm.",
                "entities": {"amount": 200, "iban": hallucinated_iban},
                "required_entities": ["amount", "iban"],
                "confirmed": True,
                "operation": "wire_transfer",
            },
        )
        rule_ids_failed = {r.rule_id for r in result.rule_results if not r.matched}
        assert "specialized.entities_in_dialog" in rule_ids_failed
        assert result.flagged  # strict predicate

    def test_invalid_iban_format_flagged(self) -> None:
        rs = specialized_agent_rules()
        bad_iban = "ES00000000000000000000"  # fails mod-97
        result = rs.evaluate(
            question=f"send 100 to {bad_iban}",
            response="OK.",
            metadata={
                "dialog": f"send 100 to {bad_iban}. yes confirm.",
                "entities": {"amount": 100, "iban": bad_iban},
                "required_entities": ["amount", "iban"],
                "confirmed": True,
            },
        )
        rule_ids_failed = {r.rule_id for r in result.rule_results if not r.matched}
        assert "specialized.iban_format_valid" in rule_ids_failed

    def test_missing_required_entity_flagged(self) -> None:
        rs = specialized_agent_rules()
        result = rs.evaluate(
            question="transfer money",
            response="To whom?",
            metadata={
                "dialog": "transfer money.",
                "entities": {"amount": 500},
                "required_entities": ["amount", "iban"],
                "confirmed": False,
            },
        )
        rule_ids_failed = {r.rule_id for r in result.rule_results if not r.matched}
        assert "specialized.required_entities_present" in rule_ids_failed

    def test_phantom_entity_flagged(self) -> None:
        rs = specialized_agent_rules()
        valid_iban = "ES9121000418450200051332"
        result = rs.evaluate(
            question="send 500",
            response="OK.",
            metadata={
                "dialog": f"send 500 to {valid_iban}. yes confirm.",
                "entities": {
                    "amount": 500,
                    "iban": valid_iban,
                    "memo": "for vacation",  # not in required_entities
                },
                "required_entities": ["amount", "iban"],
                "confirmed": True,
            },
        )
        rule_ids_failed = {r.rule_id for r in result.rule_results if not r.matched}
        assert "specialized.no_phantom_entities" in rule_ids_failed

    def test_execution_claim_without_confirmation_flagged(self) -> None:
        rs = specialized_agent_rules()
        valid_iban = "ES9121000418450200051332"
        result = rs.evaluate(
            question="send 500",
            response="I have transferred 500 EUR successfully.",
            metadata={
                "dialog": f"send 500 to {valid_iban}.",
                "entities": {"amount": 500, "iban": valid_iban},
                "required_entities": ["amount", "iban"],
                "confirmed": False,  # NOT confirmed yet
            },
        )
        rule_ids_failed = {r.rule_id for r in result.rule_results if not r.matched}
        assert "specialized.no_pre_execution_claim" in rule_ids_failed

    def test_strict_flag_predicate_triggers_at_low_groundedness(self) -> None:
        rs = specialized_agent_rules()
        # entity_groundedness collapses → flagged
        result = rs.evaluate(
            question="send 200",
            response="OK.",
            metadata={
                "dialog": "send 200.",
                "entities": {
                    "amount": 200,
                    "iban": "ES8200810098000000000001",  # not in dialog, bad format
                },
                "required_entities": ["amount", "iban"],
                "confirmed": True,
            },
        )
        assert result.flagged


# ── rag_rules ────────────────────────────────────────────────────────────────


class TestRagRules:
    def test_factory_returns_ruleset(self) -> None:
        rs = rag_rules()
        assert isinstance(rs, RuleSet)
        # Currently aliases groundlens_banking_rules
        assert rs.name.startswith("groundlens_banking")
        assert len(rs.rules) == 20

    def test_unsupported_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="legal"):
            rag_rules(domain="legal")

    def test_default_domain_is_banking(self) -> None:
        rs1 = rag_rules()
        rs2 = rag_rules(domain="banking")
        assert rs1.name == rs2.name
        assert len(rs1.rules) == len(rs2.rules)


# ── Cross-cutting ────────────────────────────────────────────────────────────


class TestAgentRuleSetsCrossCutting:
    def test_all_three_factories_callable_and_distinct(self) -> None:
        routing = routing_rules()
        specialized = specialized_agent_rules()
        rag = rag_rules()
        assert routing.name != specialized.name != rag.name

    def test_all_rule_ids_unique_across_factories(self) -> None:
        all_ids: list[str] = []
        for factory in (routing_rules, specialized_agent_rules, rag_rules):
            rs = factory()
            for rule in rs.rules:
                all_ids.append(rule.id)
        # Within each ruleset, ids must be unique; across rulesets we expect
        # distinct namespacing (routing.* vs specialized.* vs banking.*/eu_ai_act.*/etc.).
        assert len(all_ids) == len(set(all_ids))
