# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens[openai]"]
# ///
"""OpenAI provider with groundlens hallucination guard.

Requires: ``pip install groundlens[openai]``

Uses GroundlensOpenAI to wrap OpenAI chat completions with automatic
hallucination scoring. Every response includes a groundlens score.
"""

import os

from groundlens.providers.openai import GroundlensOpenAI

if __name__ == "__main__":
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Set OPENAI_API_KEY environment variable to run this example.")
        raise SystemExit(1)

    llm = GroundlensOpenAI(api_key=api_key, model="gpt-4o")

    # With context — uses SGI scoring
    print("=== With Context (SGI) ===\n")
    context = (
        "The Eiffel Tower was built for the 1889 World's Fair. "
        "It stands 330 metres tall and is located on the Champ de Mars in Paris."
    )
    resp = llm.chat("How tall is the Eiffel Tower?", context=context)
    print(f"Response: {resp.text}")
    print(f"Score:    {resp.groundlens_score.method.upper()} = {resp.groundlens_score.value:.3f}")
    print(f"Flagged:  {resp.groundlens_score.flagged}")
    print(f"Explain:  {resp.groundlens_score.explanation}\n")

    # Without context — uses DGI scoring
    print("=== Without Context (DGI) ===\n")
    resp = llm.chat("What is the speed of sound?")
    print(f"Response: {resp.text}")
    print(f"Score:    {resp.groundlens_score.method.upper()} = {resp.groundlens_score.value:.3f}")
    print(f"Flagged:  {resp.groundlens_score.flagged}")
    print(f"Explain:  {resp.groundlens_score.explanation}")
