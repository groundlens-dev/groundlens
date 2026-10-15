# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""``groundlens``: the CLI. Same engine as the Python API.

Exit codes: 0 PASS (ALLOW for a run), 1 FAIL (DENY), 2 error, 3 REVIEW.

The standalone ``glv`` binary, for auditors without Python, only checks:
``glv record verify``, ``glv run check``, ``glv policy lint|show``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from groundlens import ENGINE_VERSION, __version__, _engine
from groundlens.policy import Policy, PolicyError
from groundlens.record import IntegrityError, Record
from groundlens.report import write_report
from groundlens.run import RunRecord, verify_run
from groundlens.verify import verify

EXIT = {"PASS": 0, "FAIL": 1, "REVIEW": 3}


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _source(spec: str) -> tuple[str, str]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError("--source expects id=path")
    ident, path = spec.split("=", 1)
    return ident, _read(path)


def _chains(names: list[str]) -> list[list[Record]]:
    """Read chains: each file is one; a directory means every .jsonl in it.
    Every chain is verified before anything is computed from it."""
    files: list[Path] = []
    for name in names:
        path = Path(name)
        files.extend(sorted(path.glob("*.jsonl")) if path.is_dir() else [path])
    if not files:
        raise ValueError("no .jsonl files to verify")
    chains = [Record.read_log(f) for f in files]
    Record.verify_chains(chains)
    return chains


def _emit(doc: dict, out: str | None) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"ok  signed {doc['kind']} written to {out}")
    else:
        print(text)


def _scope(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError("--scope expects key=value")
        key, value = pair.split("=", 1)
        out[key] = value
    return out


def _with_provenance(sources: list[tuple[str, str]], specs: list[str]) -> list[tuple[str, str, dict[str, str]]]:
    provenance: dict[str, dict[str, str]] = {ident: {} for ident, _ in sources}
    for spec in specs:
        ident, sep, pair = spec.rpartition(":")
        if not sep or "=" not in pair:
            raise ValueError("--provenance expects id:key=value")
        if ident not in provenance:
            raise ValueError(f"--provenance names an unknown source id {ident!r}")
        key, value = pair.split("=", 1)
        provenance[ident][key] = value
    return [(ident, text, provenance[ident]) for ident, text in sources]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="groundlens", description="GroundLens: guardrails for LLM answers.")
    p.add_argument("--version", action="version", version=f"groundlens {__version__} (GLV engine {ENGINE_VERSION})")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify", help="verify an answer against its sources under a policy")
    v.add_argument("--answer", required=True, help="file with the model output")
    v.add_argument("--source", action="append", default=[], type=_source, help="id=path, repeatable")
    v.add_argument("--question", help="file with the question (never a source)")
    v.add_argument("--policy", default=None, help="built-in name, path or YAML; default groundlens_default_v1")
    v.add_argument("--rules", action="append", default=[], help="rule set JSON/YAML, repeatable")
    v.add_argument("--locale", default="und")
    v.add_argument("--log", help="append the signed record to this JSON Lines file")
    v.add_argument("--signing-key", help="32-byte hex Ed25519 seed (or GROUNDLENS_SIGNING_KEY)")
    v.add_argument("--no-units", action="store_true", help="groundlens 3.x bare-number semantics")
    v.add_argument("--rounding", default="within_last_digit", choices=["half_up", "half_even", "within_last_digit"], help="how a recomputed figure may differ from the one written")
    v.add_argument("--no-derive", action="store_true", help="do not recompute figures from the answer's own supported figures")
    v.add_argument("--scope", action="append", default=[], help="what the request is about, key=value, repeatable")
    v.add_argument("--provenance", action="append", default=[], help="provenance of a source, id:key=value, repeatable")
    v.add_argument("--risk-class", help="the risk class of this request, when the policy defines them")
    v.add_argument("--json", action="store_true", help="print the full record instead of the summary")

    r = sub.add_parser("report", help="build a verification report from a records log")
    r.add_argument("log")
    r.add_argument("--out", default="report", help="output directory")

    rec = sub.add_parser("record", help="record tools").add_subparsers(dest="sub", required=True)
    rv = rec.add_parser("verify", help="recompute hashes, links and signatures of one or more chains")
    rv.add_argument("logs", nargs="+", help="JSON Lines logs, one chain each; a directory means every .jsonl in it")

    pol = sub.add_parser("policy", help="policy tools").add_subparsers(dest="sub", required=True)
    pl = pol.add_parser("lint", help="check a policy")
    pl.add_argument("policy")
    ps = pol.add_parser("show", help="print a policy; --resolved merges extends and writes every default")
    ps.add_argument("policy")
    ps.add_argument("--resolved", action="store_true")

    run = sub.add_parser("run", help="whole agent executions").add_subparsers(dest="sub", required=True)
    rnv = run.add_parser("verify", help="verify an MCP trace under an execution policy and seal a run record")
    rnv.add_argument("--trace", required=True, help="the MCP trace, one JSON-RPC message per line")
    rnv.add_argument("--policy", required=True, help="the execution policy, YAML or JSON")
    rnv.add_argument("--run-id", required=True)
    rnv.add_argument("--system", required=True, help="the deployed system this run belongs to")
    rnv.add_argument("--system-version")
    rnv.add_argument("--started-at")
    rnv.add_argument("--log", help="append the signed run record to this JSON Lines file")
    rnv.add_argument("--signing-key", help="32-byte hex Ed25519 seed (or GROUNDLENS_SIGNING_KEY)")
    rnc = run.add_parser("check", help="recompute hashes, links and signatures of a run-record log")
    rnc.add_argument("log")

    m = sub.add_parser("measure", help="estimate the share of wrong answers among those that passed, from labels on a sample")
    m.add_argument("records", nargs="+", help="records logs or directories")
    m.add_argument("--sample", type=int, metavar="N", help="print N record ids to label, drawn per decision and risk class, without verdicts")
    m.add_argument("--seed", type=int, default=0, help="seed for --sample, recorded in the report")
    m.add_argument("--labels", help="CSV (record_id,label[,prediction]) or JSON Lines with your team's labels")
    m.add_argument("--review-minutes", type=float, help="minutes a person spends on one REVIEW")
    m.add_argument("--review-cost-per-hour", type=float, help="what an hour of review costs")
    m.add_argument("--error-cost", type=float, help="what one wrong answer that gets through costs")
    m.add_argument("--signing-key", help="32-byte hex Ed25519 seed for the report (or GROUNDLENS_SIGNING_KEY)")
    m.add_argument("--out", help="write the signed report here (JSON); default: print it")

    rp = sub.add_parser("replay", help="check past traffic under another policy and count the decisions that would change")
    rp.add_argument("--traffic", required=True, help="JSON Lines: answer, passages, question, scope, risk_class, record_id")
    rp.add_argument("--records", nargs="+", default=[], help="records logs or directories, to reuse the judge's evidence")
    rp.add_argument("--policy", required=True, help="the policy to replay under")
    rp.add_argument("--locale", default="und")
    rp.add_argument("--signing-key", help="32-byte hex Ed25519 seed for the report (or GROUNDLENS_SIGNING_KEY)")
    rp.add_argument("--out", help="write the signed report here (JSON); default: print it")

    j = sub.add_parser("judge", help="the judge").add_subparsers(dest="sub", required=True)
    jt = j.add_parser("show-template", help="print the exact prompt a judge is sent for this input")
    jt.add_argument("--answer", required=True)
    jt.add_argument("--source", action="append", default=[], type=_source, help="id=path, repeatable")
    jt.add_argument("--question")
    jt.add_argument("--policy", default=None)
    jt.add_argument("--locale", default="und")
    jt.add_argument("--scope", action="append", default=[])
    jt.add_argument("--provenance", action="append", default=[])
    jt.add_argument("--json", action="store_true", help="print the prompt as JSON")

    sub.add_parser("keygen", help="print a fresh Ed25519 signing seed")
    sub.add_parser("mcp", help='run the MCP server over stdio (needs pip install "groundlens[mcp]")')
    return p


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a legacy code page; receipts carry the
    # source text verbatim, so the CLI always writes UTF-8.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (PolicyError, IntegrityError, ValueError, FileNotFoundError, NotImplementedError, OSError) as e:
        print(f"groundlens: {e}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    import os

    if args.cmd == "verify":
        record = verify(
            _read(args.answer),
            _with_provenance(args.source, args.provenance),
            policy=args.policy,
            question=_read(args.question) if args.question else None,
            locale=args.locale,
            rules=args.rules,
            signing_key=args.signing_key or os.environ.get("GROUNDLENS_SIGNING_KEY"),
            log=args.log,
            units=not args.no_units,
            derive=not args.no_derive,
            rounding=args.rounding,
            scope=_scope(args.scope),
            risk_class=args.risk_class,
        )
        print(record.to_json(indent=2) if args.json else record.report())
        return EXIT[record.decision]
    if args.cmd == "report":
        summary = write_report(args.log, args.out)
        print(f"ok  {summary['records']} records written to {args.out}: report.md, report.json, records.jsonl, README-auditor.md")
        return 0
    if args.cmd == "measure":
        from groundlens import measure as gm  # noqa: PLC0415

        records = [r for chain in _chains(args.records) for r in chain]
        if args.sample:
            for rid in gm.sample(records, args.sample, args.seed):
                print(rid)
            return 0
        if not args.labels:
            raise ValueError("pass --labels, or --sample N to draw the records to label")
        labels, predictions = gm.read_labels(args.labels)
        content = gm.measure(
            records,
            labels,
            predictions=predictions,
            review_minutes=args.review_minutes,
            review_cost_per_hour=args.review_cost_per_hour,
            error_cost=args.error_cost,
            sample_seed=args.seed,
        )
        _emit(gm.sign("groundlens.measurement/1", content, args.signing_key or os.environ.get("GROUNDLENS_SIGNING_KEY")), args.out)
        return 0
    if args.cmd == "replay":
        from groundlens import measure as gm  # noqa: PLC0415
        from groundlens.verifier import Verifier  # noqa: PLC0415

        records = [r for chain in _chains(args.records) for r in chain] if args.records else []
        traffic = [json.loads(line) for line in _read(args.traffic).splitlines() if line.strip()]
        content = gm.replay(traffic, records, Verifier(args.policy, locale=args.locale))
        _emit(gm.sign("groundlens.replay/1", content, args.signing_key or os.environ.get("GROUNDLENS_SIGNING_KEY")), args.out)
        return 0
    if args.cmd == "record":
        chains = _chains(args.logs)
        n = Record.verify_chains(chains)
        if len(chains) == 1:
            print(f"ok  {n} records, chain intact, all signatures verify")
        else:
            print(f"ok  {n} records in {len(chains)} chains, every chain intact, all signatures verify")
        return 0
    if args.cmd == "policy":
        policy = Policy.coerce(args.policy)
        if args.sub == "show":
            print(policy.resolved_yaml if args.resolved else policy.yaml, end="")
            return 0
        print(f"ok  {policy.id} v{policy.version}  {policy.hash}")
        return 0
    if args.cmd == "run" and args.sub == "verify":
        run_record = verify_run(
            args.trace,
            args.policy,
            run_id=args.run_id,
            system=args.system,
            system_version=args.system_version,
            started_at=args.started_at,
            signing_key=args.signing_key or os.environ.get("GROUNDLENS_SIGNING_KEY"),
            log=args.log,
        )
        print(json.dumps(run_record.raw, ensure_ascii=False, indent=2))
        return {"ALLOW": 0, "DENY": 1, "REVIEW": 3}[run_record.gate]
    if args.cmd == "run":
        n = RunRecord.verify_chain(RunRecord.read_log(args.log))
        print(f"ok  {n} run records, chain intact, all signatures verify")
        return 0
    if args.cmd == "judge":
        from groundlens.verifier import Verifier  # noqa: PLC0415

        prompt = Verifier(args.policy, locale=args.locale).judge_prompt(
            answer=_read(args.answer),
            passages=_with_provenance(args.source, args.provenance),
            question=_read(args.question) if args.question else None,
            scope=_scope(args.scope),
        )
        if args.json:
            print(json.dumps(prompt, ensure_ascii=False, indent=2))
        else:
            print(f"# {prompt['template_id']} {prompt['template_hash']}")
            print(f"# prompt {prompt['prompt_hash']}")
            print(f"\n## system\n{prompt['system']}\n\n## user\n{prompt['user']}")
        return 0
    if args.cmd == "mcp":
        try:
            from groundlens.mcp.server import run  # noqa: PLC0415 - optional extra
        except ModuleNotFoundError as e:
            print(f"groundlens: {e}", file=sys.stderr)
            return 2
        run()
        return 0
    if args.cmd == "keygen":
        print(_engine.keygen())
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
