# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens"]
# ///
"""Batch evaluation — evaluate multiple items with mixed SGI and DGI.

Shows how to use ``evaluate_batch()`` on a list of items, some with
context (triggering SGI) and some without (triggering DGI).
"""

from groundlens import evaluate_batch

items = [
    # With context → SGI
    {
        "question": "What is the speed of light?",
        "response": "The speed of light in a vacuum is approximately 299,792,458 m/s.",
        "context": (
            "The speed of light in vacuum, commonly denoted c, is a universal "
            "physical constant exactly equal to 299,792,458 metres per second."
        ),
    },
    {
        "question": "Who wrote Hamlet?",
        "response": "Hamlet was written by William Shakespeare around 1600.",
        "context": "Hamlet is a tragedy written by William Shakespeare between 1599 and 1601.",
    },
    # Without context → DGI
    {
        "question": "What is the boiling point of water?",
        "response": "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
    },
    {
        "question": "What is machine learning?",
        "response": "Machine learning is a subset of artificial intelligence.",
    },
    # Potentially confabulated (no context) → DGI
    {
        "question": "What year was the Treaty of Westphalia signed?",
        "response": "The Treaty of Westphalia was signed in 1652.",
    },
]

if __name__ == "__main__":
    print("=== Batch Evaluation ===\n")

    results = evaluate_batch(items)

    for item, score in zip(items, results, strict=False):
        flag_marker = "FLAGGED" if score.flagged else "ok"
        print(
            f"[{flag_marker:>7}] {score.method.upper()} {score.value:+.3f}  "
            f"Q: {item['question'][:50]}"
        )

    print(f"\nTotal: {len(results)}  Flagged: {sum(1 for r in results if r.flagged)}")
