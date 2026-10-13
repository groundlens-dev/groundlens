# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""measure and replay."""

from __future__ import annotations

import json
import math
import subprocess
import sys

import pytest

import groundlens as gl
from groundlens import measure as gm
from groundlens.record import IntegrityError

POLICY = """id: desk
version: 1.0.0
extends: eu_ai_act_high_risk_v1
risk_classes:
  default: routine
  mandatory_review: [recommendation]
"""

SOURCE = [("10k#p1", "Revenue was €10M in 2024.")]


def traffic(n_right=30, n_wrong=6, n_rec=4):
    rows = []
    for i in range(n_right):
        rows.append({"answer": "Revenue was €10M in 2024.", "passages": [{"id": "10k#p1", "text": SOURCE[0][1]}], "risk_class": "routine", "i": i})
    for i in range(n_wrong):
        rows.append({"answer": "Revenue was €15M in 2024.", "passages": [{"id": "10k#p1", "text": SOURCE[0][1]}], "risk_class": "routine", "i": i})
    for i in range(n_rec):
        rows.append({"answer": "Revenue was €10M in 2024.", "passages": [{"id": "10k#p1", "text": SOURCE[0][1]}], "risk_class": "recommendation", "i": i})
    return rows


@pytest.fixture
def logged(tmp_path):
    v = gl.Verifier(POLICY, signer=gl.signers.local_key(), sink=gl.sinks.jsonl(tmp_path))
    rows = traffic()
    for row in rows:
        r = v.check(answer=row["answer"], passages=[(p["id"], p["text"]) for p in row["passages"]], risk_class=row["risk_class"])
        row["record_id"] = r.record_id
    return tmp_path, rows, gl.sinks.jsonl(tmp_path).records()


def test_sample_is_stratified_blind_and_repeatable(logged):
    _, _, records = logged
    picked = gm.sample(records, n=10, seed=7)
    assert picked == gm.sample(records, n=10, seed=7)
    decisions = {r.record_id: r.decision for r in records}
    assert {decisions[i] for i in picked} == {"PASS", "FAIL", "REVIEW"}, "every stratum is sampled"
    assert all(i.startswith("rec_") for i in picked), "ids only, no verdict"


def test_the_estimate_is_agresti_coull_within_strata():
    p, var = gm._agresti(1, 20)
    z2 = gm.Z95**2
    assert p == pytest.approx((1 + z2 / 2) / (20 + z2))
    assert var == pytest.approx(p * (1 - p) / (20 + z2))


def test_measure_reports_wrong_among_passed_cost_and_is_signed(logged):
    _, rows, records = logged
    passed = [r for r in records if r.decision == "PASS"]
    # The team finds 2 of 20 labelled passes wrong (the checks cannot see everything).
    labels = {r.record_id: i < 2 for i, r in enumerate(passed[:20])}
    labels.update({r.record_id: True for r in records if r.decision == "FAIL"})
    report = gm.measure(records, labels, review_minutes=4, review_cost_per_hour=60, error_cost=5000, sample_seed=7)
    overall = report["wrong_among_passed"]
    p, var = gm._agresti(2, 20)
    assert overall["estimate"] == pytest.approx(p)
    assert overall["low"] == pytest.approx(max(p - gm.Z95 * math.sqrt(var), 0))
    assert "wider" in overall["note"], "20 labels cannot pin a rate down to ±5 %"
    assert report["decisions"] == {"PASS": 30, "REVIEW": 4, "FAIL": 6}
    assert set(report["by_risk_class"]) == {"routine"}
    cost = report["cost"]
    assert cost["review_total"] == pytest.approx(4 * 4 / 60 * 60)
    assert cost["expected_escaped_error_total"] == pytest.approx(30 * p * 5000)
    assert report["method"]["sample_seed"] == 7

    doc = gm.sign("groundlens.measurement/1", report)
    gm.verify_signed(doc)
    doc["content"]["wrong_among_passed"]["estimate"] = 0.0
    with pytest.raises(IntegrityError):
        gm.verify_signed(doc)


def test_a_good_prediction_narrows_the_interval(logged):
    _, _, records = logged
    passed = [r for r in records if r.decision == "PASS"]
    labels = {r.record_id: i < 2 for i, r in enumerate(passed[:20])}
    # A prediction that is right on the labelled answers and says 0.067 elsewhere.
    predictions = {r.record_id: (1.0 if labels.get(r.record_id) else 0.0) if r.record_id in labels else 0.067 for r in records}
    plain = gm.measure(records, labels)["wrong_among_passed"]
    ppi = gm.measure(records, labels, predictions=predictions)["wrong_among_passed"]
    assert ppi["high"] - ppi["low"] < plain["high"] - plain["low"]
    strata = gm.measure(records, labels, predictions=predictions)["strata"]
    assert {s["method"] for s in strata if s["decision"] == "PASS"} == {"prediction-powered"}


def test_a_stratum_without_labels_is_said_not_measured(logged):
    _, _, records = logged
    report = gm.measure(records, {})
    assert report["wrong_among_passed"]["estimate"] is None
    assert "no labels" in report["wrong_among_passed"]["note"]
    with pytest.raises(ValueError, match="not in the log"):
        gm.measure(records, {"rec_nope": True})


def test_replay_counts_the_decisions_a_new_policy_would_change(logged):
    _, rows, records = logged
    stricter = POLICY.replace("mandatory_review: [recommendation]", "mandatory_review: [recommendation, routine]").replace("id: desk", "id: desk_strict")
    report = gm.replay(rows, records, gl.Verifier(stricter))
    assert report["compared"] == 40
    assert report["transitions"]["PASS"] == {"REVIEW": 30}
    assert report["transitions"]["FAIL"] == {"FAIL": 6}
    assert report["changed"] == 30


def test_replay_reuses_the_judges_evidence_when_the_prompt_is_the_same(tmp_path):
    calls = []

    def agree(system, user):
        calls.append(1)
        import re

        ids = re.findall(r"^(c\d+): <<<", user, flags=re.M)
        return json.dumps({"claims": [{"id": i, "label": "uncertain"} for i in ids]})

    class Client:
        chat = None

        def __init__(self):
            from types import SimpleNamespace

            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: SimpleNamespace(
                model="m", choices=[SimpleNamespace(message=SimpleNamespace(content=agree(kw["messages"][0]["content"], kw["messages"][1]["content"])))])))

    judged = "id: j\nversion: 1\nextends: groundlens_default_v1\nverifiers:\n  forbidden: []\njudge: {}\n"
    v = gl.Verifier(judged, judge=gl.judges.openai_compatible(Client(), "m"), sink=gl.sinks.jsonl(tmp_path))
    r = v.check(answer="Revenue was €10M in 2024.", passages=SOURCE)
    assert r.decision == "REVIEW" and len(calls) == 1
    rows = [{"answer": "Revenue was €10M in 2024.", "passages": [{"id": "10k#p1", "text": SOURCE[0][1]}], "record_id": r.record_id}]
    # A renamed policy that only makes the judge's doubt fatal: same prompt.
    fatal = judged.replace("id: j", "id: j2").replace("judge: {}", "judge:\n  unsupported: FAIL")
    report = gm.replay(rows, [r], gl.Verifier(fatal, judge=gl.judges.openai_compatible(Client(), "m")))
    assert report["judge"] == {"reused": 1, "asked_again": 0, "not_reusable": 0}
    assert report["transitions"] == {"REVIEW": {"FAIL": 1}}
    assert len(calls) == 1, "the judge was not asked again"


def test_measure_and_replay_on_the_command_line(logged):
    path, rows, records = logged
    run = lambda *a: subprocess.run([sys.executable, "-m", "groundlens.cli", *a], capture_output=True, text=True)  # noqa: E731
    out = run("measure", str(path), "--sample", "8", "--seed", "3")
    assert out.returncode == 0 and len(out.stdout.split()) >= 6
    labels = path / "labels.csv"
    labels.write_text("record_id,label\n" + "".join(f"{i},correct\n" for i in out.stdout.split()), encoding="utf-8")
    report = path / "m.json"
    out = run("measure", str(path), "--labels", str(labels), "--seed", "3", "--out", str(report))
    assert out.returncode == 0, out.stderr
    doc = json.loads(report.read_text(encoding="utf-8"))
    assert doc["kind"] == "groundlens.measurement/1"
    gm.verify_signed(doc)

    t = path / "traffic.jsonl"
    t.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    out = run("replay", "--traffic", str(t), "--records", str(path / "records.jsonl"), "--policy", POLICY)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["content"]["changed"] == 0
