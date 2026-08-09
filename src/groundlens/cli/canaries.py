"""The ``groundlens canaries`` subcommand.

Runs a canary suite and prints the section 8 metrics table. Exit status is
1 if any case in a *dev* suite failed, 0 otherwise.

The frozen suite never sets the exit status, whatever it reports. A gate on
frozen numbers would create an incentive to edit the frozen cases until the
build went green, and the frozen suite is the only thing in the repository
that is not allowed to move.

This module lives outside ``cli/main.py``'s heavy-import path on purpose:
the control path depends on pyyaml and nothing else, and running canaries
must not require the geometry extra to be installed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from groundlens.canaries import CanaryError, iter_outcomes, run_all
from groundlens.metrics import compute_metrics, render_cross_tab, render_noise, render_table

if TYPE_CHECKING:
    import argparse


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``canaries`` subcommand on an existing subparser set."""
    parser = subparsers.add_parser(
        "canaries",
        help="Run a canary suite and report escalation rate per defect class.",
        description=(
            "Run the canary cases for every rule pack and report recall, "
            "escalation rate on clean traffic and extraction recall, per "
            "defect class and crossed with surface-form distance. Exits 1 on "
            "any dev-suite failure."
        ),
    )
    parser.add_argument(
        "--packs-dir",
        default="packs",
        help="Directory holding the rule packs. Default: packs",
    )
    parser.add_argument(
        "--suite",
        default="dev",
        choices=("dev", "frozen"),
        help=(
            "Which suite to run. 'dev' is gated and sets the exit status. "
            "'frozen' reports and never gates. Default: dev"
        ),
    )
    parser.add_argument(
        "--pack",
        default=None,
        help="Run only this pack. Default: every pack that has the suite.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print the primary table only, without the cross-tabulation.",
    )


def run(args: argparse.Namespace) -> None:
    """Handle the ``canaries`` subcommand."""
    try:
        reports = run_all(args.packs_dir, args.suite)
    except CanaryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.pack is not None:
        reports = tuple(report for report in reports if report.pack == args.pack)
        if not reports:
            print(
                f"Error: no pack named {args.pack!r} with a {args.suite!r} suite "
                f"under {Path(args.packs_dir)}.",
                file=sys.stderr,
            )
            sys.exit(2)

    if not reports:
        print(
            f"Error: no pack under {Path(args.packs_dir)} has a {args.suite!r} "
            "canary suite. A pack with no canaries has never been measured.",
            file=sys.stderr,
        )
        sys.exit(2)

    outcomes = iter_outcomes(reports)
    table = compute_metrics(outcomes)

    print(f"groundlens canaries: suite {args.suite!r}, {table.total_cases} cases")
    for report in reports:
        print(
            f"  {report.pack:<24} {len(report.outcomes):>3} cases, "
            f"{len(report.failed):>3} failed  ({report.directory})"
        )
    print()
    print(render_table(table))
    print()
    print(render_noise(table))

    if not args.quiet:
        print()
        print("defect class crossed with surface-form distance:")
        print(render_cross_tab(table))

    if table.failures:
        print()
        print(f"failures ({len(table.failures)}):")
        for failure in table.failures:
            print(f"  {failure}")

    if args.suite == "frozen":
        print()
        print(
            "The frozen suite reports and does not gate. Its numbers are only "
            "worth reading because nobody was allowed to tune against them."
        )
        sys.exit(0)

    failed = sum(len(report.failed) for report in reports)
    if failed:
        print()
        print(f"{failed} dev canary case(s) did not match their expected outcome.")
        sys.exit(1)
    sys.exit(0)
