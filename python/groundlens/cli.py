"""``groundlens``: the CLI. Same engine as the Python API and the Rust binary.

Exit codes: 0 PASS, 1 FAIL, 2 error, 3 REVIEW.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from groundlens import ENGINE_VERSION, __version__, _engine
from groundlens.bundle import Bundle, BundleError
from groundlens.policy import Policy, PolicyError
from groundlens.record import IntegrityError, Record
from groundlens.report import write_report
from groundlens.verify import verify

EXIT = {"PASS": 0, "FAIL": 1, "REVIEW": 3}


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _source(spec: str) -> tuple[str, str]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError("--source expects id=path")
    ident, path = spec.split("=", 1)
    return ident, _read(path)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="groundlens", description="GroundLens: the verification and evidence layer for AI.")
    p.add_argument("--version", action="version", version=f"groundlens {__version__} (GLV engine {ENGINE_VERSION})")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify", help="verify an answer against its sources under a policy")
    v.add_argument("--answer", required=True, help="file with the model output")
    v.add_argument("--source", action="append", default=[], type=_source, help="id=path, repeatable")
    v.add_argument("--question", help="file with the question (never a source)")
    v.add_argument("--policy", default=None, help="built-in name, path or YAML; default groundlens_default_v1")
    v.add_argument("--rules", action="append", default=[], help="rule set JSON/YAML, repeatable")
    v.add_argument("--locale", default="und")
    v.add_argument("--bundle", help="bundle directory; its hash goes into the record")
    v.add_argument("--log", help="append the signed record to this JSON Lines file")
    v.add_argument("--signing-key", help="32-byte hex Ed25519 seed (or GROUNDLENS_SIGNING_KEY)")
    v.add_argument("--no-units", action="store_true", help="groundlens 3.x bare-number semantics")
    v.add_argument("--json", action="store_true", help="print the full record instead of the summary")

    r = sub.add_parser("report", help="build a verification report from a records log")
    r.add_argument("log")
    r.add_argument("--out", default="report", help="output directory")

    rec = sub.add_parser("record", help="record tools").add_subparsers(dest="sub", required=True)
    rv = rec.add_parser("verify", help="recompute hashes, links and signatures of a log")
    rv.add_argument("log")

    pol = sub.add_parser("policy", help="policy tools").add_subparsers(dest="sub", required=True)
    pl = pol.add_parser("lint", help="check a policy")
    pl.add_argument("policy")

    b = sub.add_parser("bundle", help="bundle tools").add_subparsers(dest="sub", required=True)
    bb = b.add_parser("build", help="write manifest.json for a bundle directory")
    bb.add_argument("root")
    bb.add_argument("--name", required=True)
    bb.add_argument("--bundle-version", required=True)
    bv = b.add_parser("verify", help="re-hash every artefact of a bundle")
    bv.add_argument("root")
    bp = b.add_parser("pull", help="fetch a published bundle (not in this build)")
    bp.add_argument("name", nargs="?", default="reference")

    sub.add_parser("keygen", help="print a fresh Ed25519 signing seed")
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
    except (PolicyError, IntegrityError, BundleError, ValueError, FileNotFoundError, NotImplementedError) as e:
        print(f"groundlens: {e}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    import os

    if args.cmd == "verify":
        record = verify(
            _read(args.answer),
            args.source,
            policy=args.policy,
            question=_read(args.question) if args.question else None,
            locale=args.locale,
            rules=args.rules,
            bundle=Bundle.open(args.bundle) if args.bundle else None,
            signing_key=args.signing_key or os.environ.get("GROUNDLENS_SIGNING_KEY"),
            log=args.log,
            units=not args.no_units,
        )
        print(record.to_json(indent=2) if args.json else record.report())
        return EXIT[record.decision]
    if args.cmd == "report":
        summary = write_report(args.log, args.out)
        print(f"ok  {summary['records']} records written to {args.out}: report.md, report.json, records.jsonl, README-auditor.md")
        return 0
    if args.cmd == "record":
        n = Record.verify_chain(Record.read_log(args.log))
        print(f"ok  {n} records, chain intact, all signatures verify")
        return 0
    if args.cmd == "policy":
        policy = Policy.coerce(args.policy)
        print(f"ok  {policy.id} v{policy.version}  {policy.hash}")
        return 0
    if args.cmd == "bundle":
        if args.sub == "build":
            b = Bundle.build(args.root, name=args.name, version=args.bundle_version)
            print(f"ok  {b.name} v{b.version}  {b.hash}")
        elif args.sub == "verify":
            b = Bundle.open(args.root)
            print(f"ok  {b.name} v{b.version}  {b.hash}")
        else:
            Bundle.pull(args.name)
        return 0
    if args.cmd == "keygen":
        print(_engine.keygen())
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
