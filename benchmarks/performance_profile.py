# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens"]
# ///
"""Performance profiling — measure latency and throughput for SGI and DGI.

Runs repeated evaluations and reports p50, p95, p99 latency percentiles
and throughput (evaluations per second). The first evaluation includes
model loading time; subsequent evaluations measure steady-state latency.
"""

from __future__ import annotations

import statistics
import time

from groundlens.dgi import compute_dgi
from groundlens.sgi import compute_sgi

# Test data — varied lengths to capture realistic performance.
SGI_CASES = [
    {
        "question": "What is the capital of France?",
        "context": "France is a country in Western Europe. Its capital city is Paris.",
        "response": "The capital of France is Paris.",
    },
    {
        "question": "How does photosynthesis work?",
        "context": (
            "Photosynthesis is the process by which green plants and certain "
            "other organisms transform light energy into chemical energy. During "
            "photosynthesis, plants capture light energy and use it to convert "
            "water, carbon dioxide, and minerals into oxygen and energy-rich "
            "organic compounds."
        ),
        "response": (
            "Photosynthesis converts light energy into chemical energy, "
            "transforming CO2 and water into glucose and oxygen."
        ),
    },
    {
        "question": "What is CRISPR-Cas9?",
        "context": (
            "CRISPR-Cas9 is a genome editing technology adapted from a "
            "naturally occurring bacterial immune defense system."
        ),
        "response": "CRISPR-Cas9 is a tool for editing DNA sequences in living organisms.",
    },
]

DGI_CASES = [
    {
        "question": "What is the speed of light?",
        "response": "The speed of light is approximately 299,792,458 metres per second.",
    },
    {
        "question": "Who developed the theory of relativity?",
        "response": (
            "Albert Einstein developed the theory of relativity in the early 20th century."
        ),
    },
    {
        "question": "What is machine learning?",
        "response": (
            "Machine learning is a branch of artificial intelligence that "
            "enables systems to learn from data without being explicitly programmed."
        ),
    },
]


def percentile(data: list[float], p: float) -> float:
    """Compute the p-th percentile of a sorted list."""
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def profile_sgi(iterations: int = 50) -> list[float]:
    """Profile SGI evaluation latency."""
    timings: list[float] = []

    for _ in range(iterations):
        for case in SGI_CASES:
            start = time.perf_counter()
            compute_sgi(
                question=case["question"],
                context=case["context"],
                response=case["response"],
            )
            elapsed = time.perf_counter() - start
            timings.append(elapsed)

    return timings


def profile_dgi(iterations: int = 50) -> list[float]:
    """Profile DGI evaluation latency."""
    timings: list[float] = []

    for _ in range(iterations):
        for case in DGI_CASES:
            start = time.perf_counter()
            compute_dgi(
                question=case["question"],
                response=case["response"],
            )
            elapsed = time.perf_counter() - start
            timings.append(elapsed)

    return timings


def report(name: str, timings: list[float]) -> None:
    """Print a latency report for a set of timings."""
    total_time = sum(timings)
    throughput = len(timings) / total_time if total_time > 0 else 0

    print(f"\n  {name}")
    print(f"  {'─' * 40}")
    print(f"  Evaluations:  {len(timings)}")
    print(f"  Total time:   {total_time:.2f}s")
    print(f"  Throughput:   {throughput:.1f} evals/s")
    print(f"  Mean:         {statistics.mean(timings) * 1000:.1f}ms")
    print(f"  Median (p50): {percentile(timings, 50) * 1000:.1f}ms")
    print(f"  p95:          {percentile(timings, 95) * 1000:.1f}ms")
    print(f"  p99:          {percentile(timings, 99) * 1000:.1f}ms")
    print(f"  Min:          {min(timings) * 1000:.1f}ms")
    print(f"  Max:          {max(timings) * 1000:.1f}ms")


if __name__ == "__main__":
    iterations = 50

    print("=" * 50)
    print("  GROUNDLENS PERFORMANCE PROFILE")
    print("=" * 50)
    print(f"\n  Iterations per case: {iterations}")
    print(f"  SGI test cases: {len(SGI_CASES)}")
    print(f"  DGI test cases: {len(DGI_CASES)}")

    # Warm up — load the embedding model.
    print("\n  Warming up (loading embedding model)...")
    warmup_start = time.perf_counter()
    compute_sgi(
        question="warmup",
        context="warmup context",
        response="warmup response",
    )
    warmup_time = time.perf_counter() - warmup_start
    print(f"  Model loaded in {warmup_time:.2f}s")

    # Profile SGI.
    print(f"\n  Profiling SGI ({iterations * len(SGI_CASES)} evaluations)...")
    sgi_timings = profile_sgi(iterations)
    report("SGI (Semantic Grounding Index)", sgi_timings)

    # Profile DGI.
    print(f"\n  Profiling DGI ({iterations * len(DGI_CASES)} evaluations)...")
    dgi_timings = profile_dgi(iterations)
    report("DGI (Directional Grounding Index)", dgi_timings)

    print(f"\n{'=' * 50}")
