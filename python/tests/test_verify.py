# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

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


def test_a_5x_policy_with_thresholds_is_refused():
    old = "id: old\nversion: 1\nthresholds:\n  groundlens.lexical: { support_min: 0.6, guard_band: 0.02 }\n"
    with pytest.raises((PolicyError, ValueError), match="thresholds"):
        Policy.from_yaml(old)


def test_evidence_shapes():
    text = verify("Fee 250.", "Fee 250.")
    pairs = verify("Fee 250.", [("a", "Fee 250.")])
    dicts = verify("Fee 250.", [{"id": "a", "text": "Fee 250.", "locator": "p1"}])
    assert text.decision == pairs.decision == dicts.decision == "PASS"
    with pytest.raises(TypeError):
        verify("Fee 250.", [42])


def test_scope_fails_a_figure_taken_from_another_entity():
    sources = [
        ("IP/2007/page_75", "The company recorded an income tax provision of $1.9 billion.", {"entity": "IP"}),
        ("AAPL/2006/page_100", "Provision for income taxes was $829 million.", {"entity": "AAPL"}),
    ]
    answer = "The 2006 tax expense was $1.9 billion."
    scoped = verify(answer, sources, scope={"entity": "AAPL"}, locale="en")
    unscoped = verify(answer, sources, locale="en")
    assert (scoped.decision, unscoped.decision) == ("FAIL", "PASS")
    scope_evidence = [e for e in scoped.evidence if e.verifier_id == "groundlens.scope"]
    assert scope_evidence and scope_evidence[0].result == "contradicted"
    scoped.verify()


def test_provenance_accepts_dicts_and_missing_provenance_goes_to_review():
    r = verify(
        "Revenue was $10 million.",
        [{"id": "s", "text": "Revenue was $10 million."}],
        scope={"entity": "ACME"},
        locale="en",
    )
    assert r.decision == "REVIEW"
    ok = verify(
        "Revenue was $10 million.",
        [{"id": "s", "text": "Revenue was $10 million.", "provenance": {"entity": "ACME"}}],
        scope={"entity": "ACME"},
        locale="en",
    )
    assert ok.decision == "PASS"


def test_no_model_runs():
    sources = [("s", "The total amount due is 10,000 dollars.")]
    record = verify("The invoice total is 1,000 dollars.", sources, locale="en")
    assert record.bundle_hash == "sha256:unbundled"
    assert {e.verifier_id for e in record.evidence} == {"groundlens.numeric"}


def test_figures_the_answer_computed_are_recomputed_under_the_rounding_rule():
    sources = [("10-K", "net cash provided by operating activities $1,410.5 million; cash flow $957.4 million; payout 31.0%")]
    answer = "Cash flow was $957.4 million of $1,410.5 million, or 67.8%."
    strict = verify(answer, sources, locale="en", rounding="half_up")
    assert strict.decision == "FAIL"  # 67.876… rounds half up to 67.9
    lenient = verify(answer, sources, locale="en")  # within_last_digit, the default since 6.0.3
    assert lenient.decision == "PASS"
    derived = [e for e in lenient.evidence if "derived" in e.notes]
    assert derived and "$957.4 million / $1,410.5 million" in derived[0].rationale
    off = verify(answer, sources, locale="en", rounding="within_last_digit", derive=False)
    assert off.decision == "FAIL"
    with pytest.raises(ValueError, match="rounding"):
        verify(answer, sources, rounding="nearest")


def test_a_figure_of_another_kind_than_the_question_asked_goes_to_review():
    sources = [("AAL/2013/page_172", "single-dip equity obligations | 1,246 | total obligations | 5,424")]
    question = "What portion of the total obligations is related to single-dip equity obligations?"
    amount = verify("The portion is $1,246 million.", sources, question=question, locale="en")
    assert amount.decision == "REVIEW"
    assert any("intent_mismatch" in e.notes for e in amount.evidence if e.verifier_id == "groundlens.intent")
    share = verify("It is 1,246 of 5,424, or 22.97%.", sources, question=question, locale="en")
    assert share.decision == "PASS"


DESK = (
    "id: desk\nversion: 2\nextends: eu_ai_act_high_risk_v1\n"
    "pass_means: may be shown to the analyst\n"
    "scope:\n  required: [entity]\n"
    "risk_classes:\n  default: routine\n  mandatory_review: [recommendation]\n"
)


def test_a_policy_extends_a_shipped_one_and_hashes_the_resolved_policy():
    desk = Policy.from_yaml(DESK)
    assert (desk.id, desk.version) == ("desk", "2")
    resolved = desk.resolved_yaml
    assert desk.hash in resolved.splitlines()[1]
    assert "regulatory_mapping" in resolved
    assert Policy.from_yaml(resolved).hash == desk.hash
    assert Policy.builtin("eu_ai_act_high_risk_v1").hash != desk.hash


def test_an_unknown_policy_key_is_an_error():
    with pytest.raises(ValueError, match="unknown field"):
        Policy.from_yaml("id: x\nversion: 1\nrouding: half_even\n")


def test_required_scope_risk_class_and_pass_means_reach_the_record():
    source = ("10k", "Revenue was €10M.", {"entity": "ACME"})
    missing = verify("Revenue was €10M.", [source], policy=DESK)
    assert missing.decision == "REVIEW"
    assert missing.reasons[0].startswith("missing_scope")
    assert (missing.risk_class, missing.pass_means) == ("routine", "may be shown to the analyst")
    missing.verify()

    ok = verify("Revenue was €10M.", [source], policy=DESK, scope={"entity": "ACME"})
    assert ok.decision == "PASS"
    reviewed = verify("Revenue was €10M.", [source], policy=DESK, scope={"entity": "ACME"}, risk_class="recommendation")
    assert reviewed.decision == "REVIEW"
    assert reviewed.reasons[0].startswith("mandatory_review")
    with pytest.raises(ValueError, match="no risk class"):
        verify("Revenue was €10M.", [source], policy=DESK, scope={"entity": "ACME"}, risk_class="recomendation")


def test_a_rounding_rule_in_the_policy_wins_over_the_request():
    answer = "Revenue was 2,345 against costs of 1,000, a ratio of 2.35."
    sources = [("s", "Revenue was 2,345. Costs were 1,000.")]
    banker = "id: banker\nversion: 1\nextends: groundlens_default_v1\nrounding: half_even\n"
    by_policy = verify(answer, sources, policy=banker)
    by_both = verify(answer, sources, policy=banker, rounding="half_up")
    plain = verify(answer, sources)
    assert [e.result for e in by_policy.evidence] == [e.result for e in by_both.evidence]
    assert [e.result for e in by_policy.evidence] != [e.result for e in plain.evidence]


def test_two_passages_with_the_same_id_do_not_crash_and_show_their_own_text():
    """Chunks of one page often share the page id. A figure found in the second
    chunk used to be sliced out of the first one, which aborted the process
    when the first chunk was shorter."""
    r = verify(
        answer="Revenue was €42.1 million in 2015.",
        evidence=[
            ("10k/page_7", "Short intro."),
            ("10k/page_7", "Further down the same page, revenue reached €42.1 million in 2015."),
        ],
    )
    assert r.decision == "PASS"
    shown = {e.source_text for e in r.evidence if e.verifier_id == "groundlens.numeric"}
    assert shown == {"€42.1 million", "2015"}
