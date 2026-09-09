#!/usr/bin/env python3
"""Pin every GitHub Action in the workflow sources to a commit hash and
install them into .github/workflows/.

The editable sources live in scripts/workflows/*.yml with symbolic refs
(`actions/checkout@v4`). This script resolves each ref to the commit it
points at today, through `gh api`, and writes
`.github/workflows/<name>.yml` with `uses: owner/repo@<sha> # <ref>`.
Dependabot then keeps the hashes current from the comments.

    python scripts/pin_actions.py          # resolve and install
    python scripts/pin_actions.py --check  # fail if the installed files are stale

Requires the GitHub CLI, logged in (`gh auth status`).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts" / "workflows"
DST = ROOT / ".github" / "workflows"
USES = re.compile(r"^(\s*-?\s*uses:\s*)([\w.-]+/[\w.-]+(?:/[\w./-]+)?)@([\w./-]+)(\s*(?:#.*)?)$")


def gh(path: str) -> dict | list | None:
    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return json.loads(proc.stdout)


def resolve(repo: str, ref: str, cache: dict[tuple[str, str], str]) -> str:
    key = (repo, ref)
    if key in cache:
        return cache[key]
    owner_repo = "/".join(repo.split("/")[:2])  # github/codeql-action/upload-sarif → github/codeql-action
    sha = None
    for kind in ("tags", "heads"):
        data = gh(f"repos/{owner_repo}/git/ref/{kind}/{ref}")
        if not data:
            continue
        obj = data["object"]
        if obj["type"] == "tag":  # annotated tag: dereference to the commit
            tag = gh(f"repos/{owner_repo}/git/tags/{obj['sha']}")
            sha = tag["object"]["sha"] if tag else None
        else:
            sha = obj["sha"]
        if sha:
            break
    if not sha:
        sys.exit(f"could not resolve {repo}@{ref}")
    cache[key] = sha
    return sha


def render(text: str, cache: dict) -> str:
    out = []
    for line in text.splitlines():
        m = USES.match(line)
        if m:
            prefix, repo, ref, _tail = m.groups()
            sha = resolve(repo, ref, cache)
            line = f"{prefix}{repo}@{sha} # {ref}"
        out.append(line)
    return "\n".join(out) + "\n"


def main() -> None:
    check = "--check" in sys.argv
    cache: dict[tuple[str, str], str] = {}
    stale = []
    DST.mkdir(parents=True, exist_ok=True)
    for src in sorted(SRC.glob("*.yml")):
        rendered = render(src.read_text(encoding="utf-8"), cache)
        dst = DST / src.name
        if check:
            if not dst.exists() or dst.read_text(encoding="utf-8") != rendered:
                stale.append(dst.name)
        else:
            dst.write_text(rendered, encoding="utf-8")
            print(f"wrote {dst.relative_to(ROOT)}")
    # dependabot.yml has no actions to pin; it is installed alongside so the
    # whole .github configuration comes from scripts/.
    dependabot_src = ROOT / "scripts" / "dependabot.yml"
    dependabot_dst = ROOT / ".github" / "dependabot.yml"
    if check:
        if not dependabot_dst.exists() or dependabot_dst.read_text() != dependabot_src.read_text():
            stale.append("dependabot.yml")
    else:
        dependabot_dst.write_text(dependabot_src.read_text(encoding="utf-8"), encoding="utf-8")
        print("wrote .github/dependabot.yml")
    for (repo, ref), sha in sorted(cache.items()):
        print(f"  {repo}@{ref} -> {sha[:12]}")
    if stale:
        sys.exit(f"stale workflows: {', '.join(stale)}; run scripts/pin_actions.py")


if __name__ == "__main__":
    main()
