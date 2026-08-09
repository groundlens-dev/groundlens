"""Write the canonical bytes of the sample audit record to a file.

Used two ways:

* By the ``Determinism`` CI job, once per matrix cell, so a later job
  can diff the artifacts and prove that Python 3.10 on macOS and Python
  3.14 on Linux produce the same bytes.
* By a maintainer regenerating the committed fixture after an
  intentional format change::

      python tests/determinism/export_golden.py tests/determinism/golden/record.json

Regenerating is a deliberate act. If the fixture changes and you did not
mean it, the record format moved under you and the change needs a
schema bump, not a fixture refresh.

The file written is the canonical bytes followed by exactly one line
feed. The newline is not part of the record; it is there so that the
``end-of-file-fixer`` pre-commit hook has nothing to fix and cannot
silently edit the fixture out from under the test.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import _bootstrap as _bootstrap  # noqa: E402  (imported for its side effect)
from _sample import build_sample_record  # noqa: E402

from groundlens.audit_record import canonical_json, record_sha256  # noqa: E402


def main(argv: list[str]) -> int:
    """Write the canonical record to ``argv[1]`` (or stdout) and print its digest."""
    record = build_sample_record()
    blob = canonical_json(record) + b"\n"

    if len(argv) > 1:
        target = Path(argv[1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        print(f"wrote {len(blob)} bytes to {target}")
    else:
        sys.stdout.buffer.write(blob)
        sys.stdout.buffer.write(b"\n")

    print(f"record_sha256 {record_sha256(record)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
