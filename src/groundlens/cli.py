"""One command. ``groundlens score``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from groundlens._hash import anchor_payload
from groundlens._types import AnchorProfile


def _read(value: str) -> str:
    """A path if it exists, otherwise the literal text."""
    path = Path(value)
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass
    return value


def _as_json(profile: AnchorProfile) -> str:
    return json.dumps(
        {
            "score": profile.score,
            "k": profile.k,
            "n_scored": profile.n_scored,
            "n_numeral": profile.n_numeral,
            "encoder_id": profile.encoder_id,
            "profile_sha256": profile.profile_sha256,
            "warnings": list(profile.warnings),
            "weakest": [anchor_payload(a) for a in profile.weakest],
            "anchors": [anchor_payload(a) for a in profile.anchors],
        },
        indent=2,
        ensure_ascii=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="groundlens",
        description="Which words in an answer your sources don't support, and what each lost to.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("score", help="score one answer against its sources")
    run.add_argument("--answer", required=True, help="the answer text, or a path to it")
    run.add_argument(
        "--context",
        required=True,
        action="append",
        help="a source: text, a path, or id=path. Repeat for multiple sources.",
    )
    run.add_argument("--k", type=int, default=1, help="how many weakest anchors (0 = adaptive)")
    run.add_argument("--locale", default="und", help="und, en, es, de, fr, it, pt, nl, ch")
    run.add_argument("--model", default=None, help="sentence-transformers model id")
    run.add_argument("--json", action="store_true", help="machine-readable output")

    args = parser.parse_args(argv)

    # Imported here, not at module scope: `groundlens --help` must not need torch.
    from groundlens._encode import DEFAULT_MODEL, SentenceTransformerEncoder
    from groundlens.score import score

    sources: list[tuple[str, str]] = []
    for index, raw in enumerate(args.context):
        if "=" in raw and Path(raw.split("=", 1)[1]).is_file():
            identifier, path = raw.split("=", 1)
            sources.append((identifier, _read(path)))
        else:
            sources.append((f"ctx-{index}", _read(raw)))

    encoder = SentenceTransformerEncoder(args.model or DEFAULT_MODEL)
    profile = score(_read(args.answer), sources, encoder=encoder, k=args.k, locale=args.locale)

    if args.json:
        print(_as_json(profile))
        return 0

    for warning in profile.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(profile.report())
    print()
    print(
        f"score {profile.score:.3f} (mean of the {profile.k} weakest of "
        f"{profile.n_scored} anchors, {profile.n_numeral} of them numerals)"
    )
    print(f"encoder {profile.encoder_id}")
    print(f"sha256  {profile.profile_sha256}")
    print()
    print("This is not a verdict. groundlens ships no threshold; see README.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
