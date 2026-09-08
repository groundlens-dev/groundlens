"""``groundlens report``: turn a log of records into a verification report.

JSON for machines, Markdown for people. Every number in it can be
recomputed from the records, and the records can be verified offline.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from groundlens.record import Record


def summarise(records: Iterable[Record]) -> dict[str, Any]:
    records = list(records)
    decisions = Counter(r.decision for r in records)
    results: dict[str, Counter] = defaultdict(Counter)
    kinds: dict[str, Counter] = defaultdict(Counter)
    policies = Counter((r.policy_id, r.policy_hash) for r in records)
    bundles = Counter(r.bundle_hash for r in records)
    engines = Counter(r.engine_version for r in records)
    verifiers: dict[str, dict[str, Any]] = {}
    controls = Counter()
    claims_total = 0
    for r in records:
        for v in r.verifiers:
            verifiers[v["id"]] = {"version": v["version"], "kind": v["kind"], "determinism": v["determinism"]["class"], "artefacts": v.get("artefacts", [])}
        for e in r.evidence:
            results[e.verifier_id][e.result] += 1
        for c in r.claims:
            claims_total += 1
            kinds["all"][c.decision] += 1
        for m in r.regulatory_mapping:
            controls[(m["framework"], m["article"], m["control"])] += 1
    n = len(records)
    return {
        "schema": "groundlens.verification-report/1",
        "records": n,
        "claims": claims_total,
        "decisions": dict(decisions),
        "decision_rates": {k: round(v / n, 4) for k, v in decisions.items()} if n else {},
        "review_rate": round((decisions.get("REVIEW", 0)) / n, 4) if n else None,
        "fail_rate": round((decisions.get("FAIL", 0)) / n, 4) if n else None,
        "by_verifier": {vid: dict(c) for vid, c in results.items()},
        "verifiers": verifiers,
        "policies": [{"id": pid, "hash": ph, "records": c} for (pid, ph), c in policies.items()],
        "bundles": dict(bundles),
        "engine_versions": dict(engines),
        "regulatory_controls": [
            {"framework": f, "article": a, "control": c, "triggered": k} for (f, a, c), k in controls.items()
        ],
        "chain": {
            "first_record": records[0].record_id if records else None,
            "last_record": records[-1].record_id if records else None,
            "last_record_hash": records[-1].record_hash if records else None,
        },
        "operating_point": {
            "note": "FPR at 95% recall, precision, recall, AUROC and AUPRC require labelled records; "
            "pass --labels to compute them (arrives with the benchmark milestone)."
        },
    }


def to_markdown(summary: dict[str, Any]) -> str:
    lines = ["# GroundLens verification report", ""]
    lines.append(f"Records: **{summary['records']}** · Claims: **{summary['claims']}**")
    d = summary["decisions"]
    lines.append(
        f"Decisions: PASS {d.get('PASS', 0)} · REVIEW {d.get('REVIEW', 0)} · FAIL {d.get('FAIL', 0)}"
        + (f" · review rate {summary['review_rate']:.1%} · fail rate {summary['fail_rate']:.1%}" if summary["records"] else "")
    )
    lines += ["", "## By verifier", "", "| verifier | supported | contradicted | unsupported | not applicable | error |", "|---|---:|---:|---:|---:|---:|"]
    for vid, c in sorted(summary["by_verifier"].items()):
        lines.append(f"| `{vid}` | {c.get('supported', 0)} | {c.get('contradicted', 0)} | {c.get('unsupported', 0)} | {c.get('not_applicable', 0)} | {c.get('error', 0)} |")
    lines += ["", "## Policies", ""]
    for p in summary["policies"]:
        lines.append(f"- `{p['id']}` · `{p['hash']}` · {p['records']} records")
    if summary["regulatory_controls"]:
        lines += ["", "## Regulatory controls triggered", ""]
        for c in summary["regulatory_controls"]:
            lines.append(f"- {c['framework']} {c['article']} · {c['control']} · {c['triggered']} records")
    lines += ["", "## Provenance", ""]
    for vid, v in sorted(summary["verifiers"].items()):
        lines.append(f"- `{vid}` v{v['version']} · {v['kind']} · determinism `{v['determinism']}`")
    lines.append(f"- engine versions: {', '.join(summary['engine_versions'])}")
    lines.append(f"- bundles: {', '.join(summary['bundles'])}")
    ch = summary["chain"]
    lines.append(f"- chain: `{ch['first_record']}` → `{ch['last_record']}` · last hash `{ch['last_record_hash']}`")
    lines += ["", "## Operating point", "", summary["operating_point"]["note"], ""]
    lines.append("Verify offline: `groundlens record verify records.jsonl`")
    return "\n".join(lines) + "\n"


def write_report(log: str | Path, out_dir: str | Path) -> dict[str, Any]:
    records = Record.read_log(log)
    checked = Record.verify_chain(records)
    summary = summarise(records)
    summary["chain"]["verified_records"] = checked
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(to_markdown(summary), encoding="utf-8")
    (out / "records.jsonl").write_text(Path(log).read_text(encoding="utf-8"), encoding="utf-8")
    (out / "README-auditor.md").write_text(
        "# How to check this package offline\n\n"
        "1. `pip install groundlens` (no network needed afterwards).\n"
        "2. `groundlens record verify records.jsonl` recomputes every hash and signature and every chain link.\n"
        "3. `report.json` is derived from `records.jsonl` only; regenerate it with `groundlens report records.jsonl --out .`.\n"
        "4. Policies are identified by hash inside each record; the engine version and bundle hash are in `content`.\n",
        encoding="utf-8",
    )
    return summary
