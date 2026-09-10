# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The product requirements, as tests: no dependencies, no network, a CLI
that works, a report that can be recomputed."""

from __future__ import annotations

import importlib.metadata as md
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_cli_bundle_build_and_verify(tmp_path):
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies" / "p.yaml").write_text("id: p\nversion: 1\n")
    assert run("bundle", "build", str(tmp_path), "--name", "t", "--bundle-version", "1").returncode == 0
    assert run("bundle", "verify", str(tmp_path)).returncode == 0
    (tmp_path / "policies" / "p.yaml").write_text("id: p\nversion: 2\n")
    assert run("bundle", "verify", str(tmp_path)).returncode == 2
    assert run("bundle", "status").returncode == 0


def test_bundle_pull_verifies_the_archive_and_installs(tmp_path, monkeypatch):
    """pull is the one network operation; exercised here over file:// so the
    test itself stays offline."""
    import hashlib
    import tarfile

    from groundlens import Bundle
    from groundlens.bundle import BundleError

    tiny = ROOT / "crates" / "gl-onnx" / "testdata" / "tiny-bundle"
    archive = tmp_path / "tiny.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(tiny, arcname="tiny-bundle")
    url = archive.resolve().as_uri()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    # The pinned hash of `base` protects it from any other archive.
    with pytest.raises(BundleError, match="does not match the pinned"):
        Bundle.pull("base", url=url, into=tmp_path / "b0")
    assert not (tmp_path / "b0").exists()

    # A bundle this build does not know, with no hash given: refused.
    with pytest.raises(BundleError, match="pinned"):
        Bundle.pull("tiny", url=url, into=tmp_path / "b1")
    assert not (tmp_path / "b1").exists()

    # The same with its hash: installed and verified.
    with pytest.raises(BundleError, match="does not match"):
        Bundle.pull("tiny", url=url, sha256="0" * 64, into=tmp_path / "b2")
    b = Bundle.pull("tiny", url=url, sha256=digest, into=tmp_path / "b2")
    assert b.name == "tiny-test" and (tmp_path / "b2" / "manifest.json").is_file()
    assert Bundle.open(tmp_path / "b2").hash == b.hash

    # The installed bundle is what verify() picks up by default.
    monkeypatch.setenv("GROUNDLENS_BUNDLE_DIR", str(tmp_path / "b2"))
    r = run("verify", "--answer", str(EXAMPLE / "answer.txt"), "--source", f"s={EXAMPLE / 'invoice.txt'}", "--json")
    assert r.returncode == 1, r.stderr
    rec = json.loads(r.stdout)
    assert rec["content"]["bundle_hash"] == b.hash
    assert any(e["verifier_id"] == "groundlens.lexical" for e in rec["content"]["graph"]["evidence"])
    assert run("bundle", "status").stdout.startswith("ok  base v1")
