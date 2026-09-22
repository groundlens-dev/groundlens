# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""GroundLens Verification Suite: performance.

Operational numbers, reported the way infrastructure reports them: per-property
percentiles, not a single figure. Latency to verify an answer, latency to verify a
sealed record offline, record size, and throughput. It uses the deterministic
verifiers, so the numbers are the engine's, not a model's.

    pip install groundlens
    python suite/performance.py            # human report
    python suite/performance.py --json     # machine-readable

Numbers are environment-specific. The report prints the machine it ran on, the way
OpenTelemetry and Open Policy Agent publish theirs.
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time

from groundlens import Record, verify

ANSWER = "Revenue was EUR 15M and the line is 1.2 km long."
EVIDENCE = [("10k", "Revenue was EUR 10M. Line length: 1200 m.")]
N = 200
NO_LEX = dict(lexical=False)


def _percentiles(xs):
    xs = sorted(xs)
    def pct(p):
        k = max(0, min(len(xs) - 1, int(round((p / 100) * (len(xs) - 1)))))
        return xs[k]
    return {"p50": pct(50), "p95": pct(95), "p99": pct(99),
            "mean": statistics.fmean(xs), "min": xs[0], "max": xs[-1]}


def _time(fn, n):
    xs = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t0) * 1000.0)
    return xs


def run():
    verify(ANSWER, EVIDENCE, **NO_LEX)  # warm up
    rec = verify(ANSWER, EVIDENCE, **NO_LEX)

    verify_ms = _time(lambda: verify(ANSWER, EVIDENCE, **NO_LEX), N)
    check_ms = _time(rec.verify, N)
    record_bytes = len(rec.to_json().encode("utf-8"))
    v = _percentiles(verify_ms)

    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "iterations": N,
        },
        "verify_answer_ms": _percentiles(verify_ms),
        "verify_record_offline_ms": _percentiles(check_ms),
        "record_bytes": record_bytes,
        "throughput_verifications_per_sec": round(1000.0 / v["p50"], 1),
    }


def main(argv):
    r = run()
    if "--json" in argv:
        print(json.dumps(r, indent=2))
        return 0
    env = r["environment"]
    print("GroundLens Verification Performance\n")
    print(f"  environment  {env['python']} · {env['platform']}")
    print(f"               {env['iterations']} iterations, deterministic verifiers\n")
    def line(name, p):
        print(f"  {name:<26} p50 {p['p50']:.2f} ms   p95 {p['p95']:.2f} ms   p99 {p['p99']:.2f} ms")
    line("verify an answer", r["verify_answer_ms"])
    line("verify a record (offline)", r["verify_record_offline_ms"])
    print(f"  {'record size':<26} {r['record_bytes']} bytes")
    print(f"  {'throughput':<26} {r['throughput_verifications_per_sec']} verifications/sec (at p50)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
