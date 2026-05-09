# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens[anthropic]"]
# ///
"""Anthropic provider with groundlens hallucination guard.

Requires: ``pip install groundlens[anthropic]``

Demonstrates wrapping Anthropic's Claude API with groundlens scoring.
Each response is automatically evaluated for hallucination risk.
"""

import os

from groundlens.evaluate import evaluate


def anthropic_with_groundlens(question: str, context: str | None = None) -> None:
    """Call Anthropic Claude and score the response with groundlens."""
    try:
        import anthropic
    except ImportError as err:
        print("Install anthropic: pip install groundlens[anthropic]")
        raise SystemExit(1) from err

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Set ANTHROPIC_API_KEY environment variable.")
        raise SystemExit(1)

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{"role": "user", "content": question}],
    )

    response_text = message.content[0].text

    score = evaluate(
        question=question,
        response=response_text,
        context=context,
    )

    print(f"Question: {question}")
    print(f"Response: {response_text[:200]}...")
    print(f"Method:   {score.method.upper()}")
    print(f"Score:    {score.value:.3f}")
    print(f"Flagged:  {score.flagged}")
    print(f"Explain:  {score.explanation}")
    print()


if __name__ == "__main__":
    print("=== Anthropic + Groundlens ===\n")

    # With context (SGI)
    anthropic_with_groundlens(
        question="What is CRISPR?",
        context=(
            "CRISPR-Cas9 is a genome editing tool adapted from a bacterial "
            "immune defense system. It allows precise DNA modifications."
        ),
    )

    # Without context (DGI)
    anthropic_with_groundlens(
        question="What causes auroras?",
    )
