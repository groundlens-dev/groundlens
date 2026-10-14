# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The product requirements, as tests: no dependencies, no network, a CLI
that works, a report that can be recomputed."""

from __future__ import annotations

import importlib.metadata as md
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "invoice"


def run(*args, **kw):
    return subprocess.run([sys.executable, "-m", "groundlens.cli", *args], capture_output=True, text=True, **kw)


def test_no_runtime_dependencies():
    dist = md.distribution("groundlens")
    requires = [r for r in (dist.requires or []) if "extra ==" not in r]
    assert requires == [], requires


def test_no_network_modules_are_imported():
    code = (
        "import sys, groundlens, groundlens.cli, groundlens.report\n"
        "bad = [m for m in ('socket','ssl','http.client','urllib.request','requests','httpx') if m in sys.modules]\n"
        "print(json.dumps(bad)) if False else print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", "import json\n" + code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]", out.stdout


def test_cli_help_and_version():
    assert run("--help").returncode == 0
    v = run("--version")
    assert v.returncode == 0 and "GLV engine" in v.stdout


def test_cli_verify_report_record_verify(tmp_path):
    log = tmp_path / "records.jsonl"
    r = run(
        "verify", "--answer", str(EXAMPLE / "answer.txt"), "--question", str(EXAMPLE / "question.txt"),
        "--source", f"invoice.pdf#p1={EXAMPLE / 'invoice.txt'}", "--policy", "eu_ai_act_high_risk_v1",
        "--rules", str(ROOT / "rules" / "es_banking_v1.yaml"), "--locale", "en", "--log", str(log),
    )
    assert r.returncode == 1, r.stderr  # FAIL
    assert "contradicted" in r.stdout and "10,000 dollars" in r.stdout

    ok = run("verify", "--answer", str(EXAMPLE / "answer.txt"), "--source", f"s={EXAMPLE / 'answer.txt'}", "--log", str(log))
    assert ok.returncode == 0  # an answer is supported by itself

    rv = run("record", "verify", str(log))
    assert rv.returncode == 0 and "2 records" in rv.stdout

    rep = run("report", str(log), "--out", str(tmp_path / "report"))
    assert rep.returncode == 0, rep.stderr
    summary = json.loads((tmp_path / "report" / "report.json").read_text())
    assert summary["records"] == 2 and summary["decisions"] == {"FAIL": 1, "PASS": 1}
    assert (tmp_path / "report" / "README-auditor.md").exists()
    assert "eu_ai_act_high_risk_v1" in (tmp_path / "report" / "report.md").read_text()


def test_cli_policy_lint_and_keygen():
    assert run("policy", "lint", "groundlens_default_v1").returncode == 0
    assert run("policy", "lint", str(ROOT / "policies" / "eu_ai_act_high_risk_v1.yaml")).returncode == 0
    key = run("keygen").stdout.strip()
    assert len(key) == 64 and int(key, 16) >= 0


def test_cli_policy_show_resolved(tmp_path):
    child = tmp_path / "desk.yaml"
    child.write_text("id: desk\nversion: 1.0.0\nextends: eu_ai_act_high_risk_v1\nrounding: half_even\n", encoding="utf-8")
    plain = run("policy", "show", str(child))
    assert plain.returncode == 0 and plain.stdout.startswith("id: desk")
    resolved = run("policy", "show", str(child), "--resolved")
    assert resolved.returncode == 0
    assert resolved.stdout.startswith("# desk v1.0.0\n# hash: sha256:")
    assert "rounding: half_even" in resolved.stdout and "regulatory_mapping" in resolved.stdout
    lint = run("policy", "lint", str(child))
    assert lint.returncode == 0 and lint.stdout.split()[-1] in resolved.stdout


def test_cli_verifies_and_checks_an_agent_run(tmp_path):
    log = tmp_path / "runs.jsonl"
    here = ROOT / "examples" / "run"
    args = ("--policy", str(here / "execution-policy.yaml"), "--run-id", "r1", "--system", "demo", "--log", str(log))
    denied = run("run", "verify", "--trace", str(here / "trace.jsonl"), *args)
    assert denied.returncode == 1, denied.stderr  # the trace calls a denied tool
    assert json.loads(denied.stdout)["content"]["gate"] == "DENY"
    checked = run("run", "check", str(log))
    assert checked.returncode == 0 and checked.stdout.startswith("ok  1 run records")
