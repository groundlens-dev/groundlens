# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens[semantic-kernel]"]
# ///
"""Semantic Kernel filter — intercept completions for hallucination checks.

Requires: ``pip install groundlens[semantic-kernel]``

Demonstrates a GroundlensFilter that hooks into Semantic Kernel's
function invocation pipeline to automatically verify LLM outputs.
"""

from groundlens.evaluate import evaluate


class GroundlensFilter:
    """Semantic Kernel filter that scores LLM outputs with groundlens.

    In a real Semantic Kernel setup, implement the filter protocol:

        from semantic_kernel.filters import FunctionInvocationFilter

        class GroundlensFilter(FunctionInvocationFilter):
            async def on_function_invocation(self, context, next):
                await next(context)
                # Score the result...

    This example shows the scoring logic standalone.
    """

    def __init__(
        self,
        model: str = "all-MiniLM-L6-v2",
        block_on_flag: bool = False,
    ) -> None:
        """Initialize the filter.

        Args:
            model: Sentence transformer model for groundlens scoring.
            block_on_flag: If True, raise an exception when a response
                is flagged. If False, attach the score as metadata.
        """
        self.model = model
        self.block_on_flag = block_on_flag

    def verify(
        self,
        question: str,
        response: str,
        context: str | None = None,
    ) -> dict:
        """Verify a response and return structured result.

        Args:
            question: The input prompt.
            response: The LLM output to verify.
            context: Optional source context.

        Returns:
            Dict with score details and pass/fail status.

        Raises:
            RuntimeError: If ``block_on_flag`` is True and the response
                is flagged.
        """
        score = evaluate(
            question=question,
            response=response,
            context=context,
            model=self.model,
        )

        result = {
            "method": score.method,
            "value": score.value,
            "normalized": score.normalized,
            "flagged": score.flagged,
            "explanation": score.explanation,
        }

        if self.block_on_flag and score.flagged:
            msg = f"Groundlens blocked response: {score.explanation} (score={score.value:.3f})"
            raise RuntimeError(msg)

        return result


if __name__ == "__main__":
    print("=== Semantic Kernel GroundlensFilter Demo ===\n")

    # Non-blocking mode (default): attach score as metadata.
    filter_pass = GroundlensFilter(block_on_flag=False)

    result = filter_pass.verify(
        question="What is quantum computing?",
        response=(
            "Quantum computing uses quantum bits (qubits) that can exist "
            "in superposition, enabling parallel computation."
        ),
        context=(
            "Quantum computers use qubits which leverage superposition "
            "and entanglement to process information."
        ),
    )
    print(f"Method:   {result['method'].upper()}")
    print(f"Score:    {result['value']:.3f}")
    print(f"Flagged:  {result['flagged']}")
    print(f"Explain:  {result['explanation']}\n")

    # Blocking mode: raises RuntimeError on flagged responses.
    filter_block = GroundlensFilter(block_on_flag=True)
    print("Blocking mode test:")
    try:
        filter_block.verify(
            question="Who invented the telephone?",
            response="The telephone was invented by Nikola Tesla in 1895.",
        )
        print("  Response passed verification.")
    except RuntimeError as exc:
        print(f"  Blocked: {exc}")
