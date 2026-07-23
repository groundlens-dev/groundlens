"""The second-stage Check builder maps consistency to the locked vocabulary."""

from __future__ import annotations

from groundlens.check import SC_CONSISTENT, SC_MIXED, Check, check_for_verification


def test_consistent_is_ok_and_does_not_escalate() -> None:
    c = check_for_verification(0.95, n_samples=7)
    assert isinstance(c, Check)
    assert c.level == "ok"
    assert c.escalate is False
    assert c.metric_abbr == "SC"
    assert c.method == "selfcheck_nli"
    assert c.headline == "CHECK"


def test_mixed_is_review_and_escalates() -> None:
    c = check_for_verification(0.60)
    assert c.level == "review"
    assert c.escalate is True


def test_inconsistent_is_risk_and_escalates() -> None:
    c = check_for_verification(0.20)
    assert c.level == "risk"
    assert c.escalate is True


def test_boundaries() -> None:
    assert check_for_verification(SC_CONSISTENT).level == "ok"
    assert check_for_verification(SC_MIXED).level == "review"
    assert check_for_verification(SC_MIXED - 0.01).level == "risk"


def test_method_label_is_carried_through() -> None:
    assert check_for_verification(0.9, method="paraphrase_nli").method == "paraphrase_nli"
