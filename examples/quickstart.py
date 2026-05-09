# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens"]
# ///
"""Quickstart — compute SGI and DGI scores in a few lines."""

from groundlens import compute_dgi, compute_sgi

# SGI: with context (RAG verification)
sgi = compute_sgi(
    question="What is the capital of France?",
    context="France is in Western Europe. Its capital is Paris.",
    response="The capital of France is Paris.",
)
print(f"SGI: {sgi.value:.3f}  flagged={sgi.flagged}  {sgi.explanation}")

# DGI: without context (context-free verification)
dgi = compute_dgi(
    question="What causes seasons on Earth?",
    response="Seasons are caused by Earth's 23.5-degree axial tilt.",
)
print(f"DGI: {dgi.value:.3f}  flagged={dgi.flagged}  {dgi.explanation}")
