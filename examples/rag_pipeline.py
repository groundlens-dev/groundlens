# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens"]
# ///
"""RAG pipeline with groundlens verification.

Demonstrates integrating groundlens into a retrieval-augmented generation
pipeline: retrieve context, generate a response, verify with SGI, and
flag unreliable outputs. Uses mock data — no external dependencies.
"""

from groundlens import compute_sgi

# --- Mock RAG components ---------------------------------------------------

KNOWLEDGE_BASE = {
    "photosynthesis": (
        "Photosynthesis is the process by which green plants convert sunlight, "
        "water, and carbon dioxide into glucose and oxygen. It occurs primarily "
        "in the chloroplasts of leaf cells."
    ),
    "mitosis": (
        "Mitosis is a type of cell division that results in two daughter cells, "
        "each having the same number and kind of chromosomes as the parent cell."
    ),
}


def retrieve(query: str) -> str:
    """Mock retriever that matches keywords to knowledge base entries."""
    query_lower = query.lower()
    for key, text in KNOWLEDGE_BASE.items():
        if key in query_lower:
            return text
    return ""


def generate(query: str, context: str) -> str:
    """Mock LLM that returns a plausible response."""
    if "photosynthesis" in query.lower():
        return (
            "Photosynthesis converts sunlight, water, and CO2 into glucose "
            "and oxygen in the chloroplasts of plant cells."
        )
    return "I'm not sure about that topic."


# --- RAG pipeline with verification ----------------------------------------


def rag_with_verification(question: str) -> None:
    """Run a RAG query with groundlens hallucination verification."""
    context = retrieve(question)
    if not context:
        print(f"  No context found for: {question}")
        return

    response = generate(question, context)

    result = compute_sgi(
        question=question,
        context=context,
        response=response,
    )

    print(f"  Question: {question}")
    print(f"  Response: {response}")
    print(f"  SGI:      {result.value:.3f} (normalized: {result.normalized:.3f})")

    if result.flagged:
        print("  STATUS:   FLAGGED — response may not be grounded in context")
    else:
        print("  STATUS:   PASS — response appears grounded")
    print()


if __name__ == "__main__":
    print("=== RAG Pipeline with Groundlens Verification ===\n")
    rag_with_verification("What is photosynthesis?")
    rag_with_verification("Explain mitosis.")
