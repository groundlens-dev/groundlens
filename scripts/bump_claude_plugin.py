"""Point the Claude plugin at a new GroundLens release.

    python scripts/bump_claude_plugin.py 6.0.6

Sets the pinned version in plugins/groundlens/.mcp.json (the
`uvx --from groundlens[mcp]==X.Y.Z` launch), in plugins/groundlens/pyproject.toml,
and the plugin's own `version` in .claude-plugin/plugin.json. Run `uv lock` in plugins/groundlens afterwards.
The release workflow does both once PyPI serves the version.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "groundlens"
PIN = re.compile(r"groundlens\[mcp\]==[0-9][0-9A-Za-z.+-]*")


def main(version: str) -> None:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+([0-9A-Za-z.+-]*)", version):
        raise SystemExit(f"not a version: {version!r}")
    pin = f"groundlens[mcp]=={version}"

    servers = PLUGIN / ".mcp.json"
    data = json.loads(servers.read_text(encoding="utf-8"))
    args = data["mcpServers"]["groundlens"]["args"]
    hits = [i for i, a in enumerate(args) if PIN.fullmatch(a)]
    if len(hits) != 1:
        raise SystemExit(f"expected one groundlens[mcp]==… argument in {servers}, found {len(hits)}")
    args[hits[0]] = pin
    servers.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = PLUGIN / ".claude-plugin" / "plugin.json"
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    meta["version"] = version
    manifest.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    project = PLUGIN / "pyproject.toml"
    text = project.read_text(encoding="utf-8")
    new, n = PIN.subn(pin, text)
    if n != 2:  # the comment at the top and the dependency
        raise SystemExit(f"expected two groundlens[mcp]==… pins in {project}, found {n}")
    project.write_text(new, encoding="utf-8")
    print(f"plugin pinned to {pin}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
