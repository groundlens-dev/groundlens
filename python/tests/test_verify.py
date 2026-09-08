"""verify(): answer → verifier → evidence → policy → decision → signed record."""

from __future__ import annotations

import json

import pytest

from groundlens import Policy, Record, verify
from groundlens.policy import PolicyError
from groundlens.record import IntegrityError


def test_numeric_contradiction_fails_under_default_policy():
    r = verify(answer="Revenue was €15M.", evidence=[("10k", "Revenue was €10M.")])
    assert r.decision == "FAIL"
    assert r.policy_id == "groundlens_default_v1"
    e = r.evidence[0]
    assert (e.verifier_id, e.result, e.score, e.determinism) == ("groundlens.numeric", "contradicted", 0.0, "exact")
    assert e.source_text == "€10M"
    assert r.reasons and "numeric contradicted" in r.reasons[0]
    r.verify()


def test_a_verifier_never_decides_the_policy_does():
    """Same evidence, two policies, two decisions."""
    permissive = Policy.from_yaml(
        "id: permissive\nversion: 1\nverifiers:\n  required: [groundlens.numeric]\n"
        "decision:\n  any_contradiction_from: []\n  unresolved_claims: REVIEW\n  tolerate_unresolved_kinds: [word]\n"
    )
    a = verify("Revenue was €15M.", [("10k", "Revenue was €10M.")])
    b = verify("Revenue was €15M.", [("10k", "Revenue was €10M.")], policy=permissive)
    assert [e.result for e in a.evidence] == [e.result for e in b.evidence] == ["contradicted"]
    assert (a.decision, b.decision) == ("FAIL", "REVIEW")


def test_same_input_same_content_hash_distinct_records():
    a = verify("Total 1,000 dollars.", [("s", "Total 10,000 dollars.")])
    b = verify("Total 1,000 dollars.", [("s", "Total 10,000 dollars.")])
    assert a.content_hash == b.content_hash
    assert a.record_id != b.record_id


def test_units_are_compared_in_base_units():
    r = verify(
        "The line is 1.2 km long and revenue was $37.35 billion.",
        [("s", "Line length: 1200 m.\nRevenue (in millions of dollars)\n2024  37,350")],
    )
    assert r.decision == "PASS"
    assert {e.result for e in r.evidence} == {"supported"}
    legacy = verify("The line is 1.2 km long.", [("s", "Line length: 1200 m.")], units=False)
    assert legacy.decision == "FAIL"


def test_named_relaxations_are_opt_in_and_noted():
    strict = verify("About 37.4 billion.", [("s", "37,350 million")])
    assert strict.decision == "FAIL"
    relaxed = verify("About 37.4 billion.", [("s", "37,350 million")], declared_precision=True)
    assert relaxed.decision == "PASS"
    assert "matches_at_declared_precision" in relaxed.evidence[0].notes


def test_high_risk_policy_maps_to_regulation():
    r = verify(
        "The invoice total is 1,000 dollars, due in 30 days.",
        [("invoice.pdf#p1", "The total amount due is 10,000 dollars, payable within 30 days.")],
        policy="eu_ai_act_high_risk_v1",
        question="What is the invoice total?",
    )
    assert r.decision == "FAIL"
    assert [m["article"] for m in r.regulatory_mapping] == ["Art. 15(1)", "Art. 12(1)"]


def test_rules_are_a_symbolic_verifier():
    rules = {
        "id": "demo", "version": "1.0.0",
        "rules": [{
            "id": "apr_must_be_percent", "description": "an APR is a percentage",
            "scope": {"claim_kind": "numeric"},
            "when": {"answer_matches": "(?i)\\bAPR\\b"},
            "unless": {"attribute": {"dimension": "percent"}},
            "emit": "contradicted",
        }],
    }
    r = verify("The APR is 4.75 for 30 days.", [("s", "APR 4.75% for 30 days")], rules=[rules])
    assert r.decision == "FAIL"
    assert any(e.verifier_id == "groundlens.rules.demo" and e.result == "contradicted" for e in r.evidence)


def test_chain_via_log_and_tamper_detection(tmp_path):
    log = tmp_path / "records.jsonl"
    for i in range(3):
        verify(f"Total {i + 1},000 dollars", [("s", "Total 1,000 dollars")], log=log)
    records = Record.read_log(log)
    assert Record.verify_chain(records) == 3
    assert records[0].previous_record_hash is None
    assert records[1].previous_record_hash == records[0].record_hash

    tampered = json.loads(records[1].to_json())
    tampered["content"]["outcome"]["decision"] = "PASS"
    with pytest.raises(IntegrityError):
        Record.from_json(json.dumps(tampered)).verify()
    with pytest.raises(IntegrityError):
        Record.verify_chain([records[0], records[2]])


def test_policy_lint_rejects_a_narrow_guard_band():
    bad = "id: bad\nversion: 1\nthresholds:\n  groundlens.numeric: { support_min: 0.5, guard_band: 0.0 }\n"
    with pytest.raises(PolicyError):
        Policy.from_yaml(bad)


def test_evidence_shapes():
    text = verify("Fee 250.", "Fee 250.")
    pairs = verify("Fee 250.", [("a", "Fee 250.")])
    dicts = verify("Fee 250.", [{"id": "a", "text": "Fee 250.", "locator": "p1"}])
    assert text.decision == pairs.decision == dicts.decision == "PASS"
    with pytest.raises(TypeError):
        verify("Fee 250.", [42])
