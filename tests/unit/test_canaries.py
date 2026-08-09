"""Tests for the canary runner and the section 8 metrics.

These test the measuring instrument, not the packs. If the instrument is
wrong the numbers it reports are worse than no numbers, because they carry
the authority of having been measured.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from groundlens.canaries import (
    DEFECT_CLASS_FACT_KINDS,
    DEFECT_CLASSES,
    SURFACE_FORM_DISTANCES,
    CanaryError,
    load_suite,
    run_all,
    run_suite,
)
from groundlens.metrics import Rate, compute_metrics, render_cross_tab, render_noise, render_table
from groundlens.types import Decision

PACKS = Path(__file__).resolve().parents[2] / "packs"


# ── The vocabulary ──────────────────────────────────────────────────────────


def test_every_defect_class_has_a_fact_kind_entry() -> None:
    """A class with no entry would silently drop out of extraction recall."""
    assert set(DEFECT_CLASS_FACT_KINDS) == set(DEFECT_CLASSES)


def test_clean_is_a_defect_class_and_carries_no_fact_kind() -> None:
    assert "clean" in DEFECT_CLASSES
    assert DEFECT_CLASS_FACT_KINDS["clean"] == ()


def test_surface_form_distances_are_the_four_the_contract_names() -> None:
    assert SURFACE_FORM_DISTANCES == (
        "identical",
        "reformatted",
        "paraphrased",
        "restructured",
    )


# ── Loading ─────────────────────────────────────────────────────────────────


def _write(tmp_path: Path, body: str) -> Path:
    suite = tmp_path / "dev"
    suite.mkdir(parents=True, exist_ok=True)
    (suite / "cases.yaml").write_text(body, encoding="utf-8")
    return suite


_MINIMAL = """
- id: case-1
  defect_class: clean
  surface_form_distance: identical
  answer: Nothing to see here.
  evidence:
    - id: doc-1
      text: Nothing to see here.
  expect:
    decision: clear
"""


def test_load_suite_reads_a_list_of_cases(tmp_path: Path) -> None:
    cases = load_suite(_write(tmp_path, _MINIMAL))
    assert [case.id for case in cases] == ["case-1"]
    assert cases[0].expect_decision is Decision.CLEAR


def test_load_suite_rejects_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(CanaryError, match="not a canary suite directory"):
        load_suite(tmp_path / "nope")


def test_load_suite_rejects_an_unknown_defect_class(tmp_path: Path) -> None:
    body = _MINIMAL.replace("defect_class: clean", "defect_class: vibes")
    with pytest.raises(CanaryError, match="is not one of"):
        load_suite(_write(tmp_path, body))


def test_load_suite_rejects_an_unknown_surface_form(tmp_path: Path) -> None:
    body = _MINIMAL.replace("surface_form_distance: identical", "surface_form_distance: близко")
    with pytest.raises(CanaryError, match="is not one of"):
        load_suite(_write(tmp_path, body))


def test_load_suite_rejects_an_unknown_key(tmp_path: Path) -> None:
    body = _MINIMAL + "  severity: fail\n"
    with pytest.raises(CanaryError, match="unknown key"):
        load_suite(_write(tmp_path, body))


def test_load_suite_rejects_duplicate_ids(tmp_path: Path) -> None:
    with pytest.raises(CanaryError, match="is used twice"):
        load_suite(_write(tmp_path, _MINIMAL + _MINIMAL))


def test_a_clean_case_may_not_expect_an_escalation(tmp_path: Path) -> None:
    """Otherwise the false-alarm denominator could be quietly padded."""
    body = _MINIMAL.replace("decision: clear", "decision: escalate")
    with pytest.raises(CanaryError, match="is not clean"):
        load_suite(_write(tmp_path, body))


def test_load_suite_rejects_malformed_yaml(tmp_path: Path) -> None:
    with pytest.raises(CanaryError, match="not valid YAML"):
        load_suite(_write(tmp_path, "id: [unclosed\n"))


# ── Rates ───────────────────────────────────────────────────────────────────


def test_rate_renders_as_an_unreduced_fraction() -> None:
    assert str(Rate(3, 4)) == "3/4"
    assert str(Rate(75, 100)) == "75/100"


def test_rate_with_no_cases_is_not_applicable() -> None:
    assert str(Rate(0, 0)) == "n/a"
    assert not Rate(0, 0).defined


def test_rate_has_no_float_anywhere() -> None:
    rate = Rate(1, 3)
    assert not any(isinstance(value, float) for value in (rate.numerator, rate.denominator))
    assert "." not in str(rate)


def test_rate_comparison_is_integer_only() -> None:
    assert Rate(3, 4).at_least(1, 2)
    assert not Rate(1, 4).at_least(1, 2)
    assert not Rate(0, 0).at_least(0, 1)


# ── Metrics ─────────────────────────────────────────────────────────────────


def test_metrics_over_an_empty_run_do_not_divide_by_zero() -> None:
    table = compute_metrics([])
    assert table.total_cases == 0
    assert str(table.clean_escalation) == "n/a"
    assert table.rows == ()


def test_metrics_module_exposes_no_auroc() -> None:
    """Section 8 says the metric is escalation rate at fixed recall, not AUROC.

    There is no score to sweep a threshold along, so an AUROC here could
    only be manufactured, and an aggregate would hide the collapse this
    measurement exists to expose.
    """
    import groundlens.metrics as metrics

    names = [name.lower() for name in dir(metrics)]
    assert not any("auroc" in name or "auc" in name for name in names)


def test_metrics_render_without_a_single_float(tmp_path: Path) -> None:
    report = run_suite(PACKS / "eu-retail-banking", "dev")
    table = compute_metrics(report.outcomes)
    text = "\n".join(
        (render_table(table), render_cross_tab(table), render_noise(table)),
    )
    for row in table.rows:
        for rate in (row.recall, row.escalation_rate_on_clean_traffic, row.extraction_recall):
            assert isinstance(rate.numerator, int)
            assert isinstance(rate.denominator, int)
    assert "0." not in text


def test_clean_row_counts_cases_left_alone_not_cases_escalated() -> None:
    """The recall column must mean the same thing in every row."""
    report = run_suite(PACKS / "decision-rationale", "dev")
    table = compute_metrics(report.outcomes)
    clean = table.row("clean")
    assert clean is not None
    escalated = sum(
        1
        for outcome in report.outcomes
        if outcome.case.defect_class == "clean" and outcome.decision is Decision.ESCALATE
    )
    assert clean.recall.numerator == clean.cases - escalated


# ── The shipped suites ──────────────────────────────────────────────────────


@pytest.mark.parametrize("suite", ["dev", "frozen"])
def test_every_shipped_pack_has_both_suites_and_they_load(suite: str) -> None:
    reports = run_all(PACKS, suite)
    assert {report.pack for report in reports} == {"eu-retail-banking", "decision-rationale"}
    for report in reports:
        assert report.outcomes, f"{report.pack} {suite} suite is empty"


@pytest.mark.parametrize("suite", ["dev", "frozen"])
def test_clean_is_at_least_as_large_as_any_defect_class(suite: str) -> None:
    """The control group cannot be the smallest group in the suite.

    A clean class smaller than the defect classes gives a false-alarm rate
    with a denominator too small to act on, and that rate is the number the
    whole exercise exists to produce.
    """
    for report in run_all(PACKS, suite):
        table = compute_metrics(report.outcomes)
        clean = table.row("clean")
        assert clean is not None, f"{report.pack} {suite} has no clean cases"
        largest_defect = max(row.cases for row in table.rows if not row.is_clean)
        assert clean.cases >= largest_defect, (
            f"{report.pack} {suite}: clean class has {clean.cases} cases, "
            f"smaller than the largest defect class at {largest_defect}"
        )


@pytest.mark.parametrize("suite", ["dev", "frozen"])
def test_polarity_flip_covers_both_directions(suite: str) -> None:
    """must -> may and must_not -> may fail differently and both must be here."""
    for report in run_all(PACKS, suite):
        answers = " ".join(
            outcome.case.answer.casefold()
            for outcome in report.outcomes
            if outcome.case.defect_class == "polarity_flip"
        )
        evidence = " ".join(
            text.casefold()
            for outcome in report.outcomes
            if outcome.case.defect_class == "polarity_flip"
            for _, text in outcome.case.evidence
        )
        assert "must not" in evidence, f"{report.pack} {suite}: no must_not source"
        assert "may" in answers, f"{report.pack} {suite}: no permissive answer"


def test_running_a_suite_twice_gives_the_same_answer() -> None:
    """Determinism rule 7: no randomness, no hash-order dependence."""
    first = compute_metrics(run_suite(PACKS / "eu-retail-banking", "dev").outcomes)
    second = compute_metrics(run_suite(PACKS / "eu-retail-banking", "dev").outcomes)
    assert render_table(first) == render_table(second)
    assert first.failures == second.failures
