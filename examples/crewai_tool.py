# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens[crewai]"]
# ///
"""CrewAI tool integration — give agents a deterministic grounding check.

Requires: ``pip install groundlens[crewai]``

Demonstrates a GroundlensTool that CrewAI agents can use to verify
their own outputs before returning results.
"""

from groundlens.evaluate import evaluate


class GroundlensTool:
    """CrewAI-compatible tool for hallucination verification.

    Agents call this tool to check whether a response is grounded
    in source material (SGI) or aligns with known factual patterns (DGI).

    In a real CrewAI setup, inherit from ``crewai.tools.BaseTool``:

        from crewai.tools import BaseTool

        class GroundlensTool(BaseTool):
            name = "groundlens_verify"
            description = "Verify if a response is factually grounded."
            ...
    """

    name: str = "groundlens_verify"
    description: str = (
        "Verify whether a response is factually grounded. "
        "Provide question, response, and optionally context."
    )

    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        self.model = model

    def _run(self, question: str, response: str, context: str | None = None) -> str:
        """Execute the verification tool.

        Args:
            question: The original question asked.
            response: The response to verify.
            context: Optional source context for grounded verification.

        Returns:
            Human-readable verification result string.
        """
        score = evaluate(
            question=question,
            response=response,
            context=context,
            model=self.model,
        )

        status = "FLAGGED for review" if score.flagged else "PASSED"
        return (
            f"Verification: {status}\n"
            f"Method: {score.method.upper()}\n"
            f"Score: {score.value:.3f} (normalized: {score.normalized:.3f})\n"
            f"Explanation: {score.explanation}"
        )


if __name__ == "__main__":
    print("=== CrewAI GroundlensTool Demo ===\n")

    tool = GroundlensTool()

    # Simulate an agent verifying its own response.
    print("Agent verifying a grounded response:\n")
    result = tool._run(
        question="What is the function of mitochondria?",
        response=(
            "Mitochondria are the powerhouses of the cell,"
            " producing ATP through oxidative phosphorylation."
        ),
        context=(
            "Mitochondria generate most of the cell's supply of ATP,"
            " used as a source of chemical energy."
        ),
    )
    print(result)

    print("\n\nAgent verifying a suspicious response:\n")
    result = tool._run(
        question="When was the Eiffel Tower built?",
        response="The Eiffel Tower was built in 1920 by Gustave Eiffel for the Paris Olympics.",
    )
    print(result)
