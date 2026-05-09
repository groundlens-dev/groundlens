# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens[langchain]"]
# ///
"""LangChain evaluator integration with LangSmith evaluate().

Requires: ``pip install groundlens[langchain]``

Demonstrates using GroundlensEvaluator as a custom evaluator within
LangSmith's ``evaluate()`` function for systematic LLM evaluation.
"""

from typing import TYPE_CHECKING

from groundlens.evaluate import evaluate

if TYPE_CHECKING:
    from groundlens.score import GroundlensScore


class GroundlensEvaluator:
    """LangChain-compatible evaluator wrapping groundlens scoring.

    Implements the evaluator interface expected by LangSmith's
    ``evaluate()`` function. Each example is scored with SGI (if
    context is present) or DGI (if context-free).
    """

    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        self.model = model

    def __call__(self, run, example) -> dict:
        """Evaluate a single run against its example.

        Args:
            run: LangSmith Run object with ``.outputs`` dict.
            example: LangSmith Example object with ``.inputs`` and
                optionally ``.outputs`` dict.

        Returns:
            Dict with ``key``, ``score``, and ``comment`` fields.
        """
        question = example.inputs.get("question", "")
        response = run.outputs.get("output", run.outputs.get("response", ""))
        context = example.inputs.get("context")

        score: GroundlensScore = evaluate(
            question=question,
            response=response,
            context=context,
            model=self.model,
        )

        return {
            "key": f"groundlens_{score.method}",
            "score": score.normalized,
            "comment": score.explanation,
        }


if __name__ == "__main__":
    # Standalone demo without LangSmith connection.
    # In production, use with langsmith.evaluate():
    #
    #   from langsmith import evaluate as ls_evaluate
    #   results = ls_evaluate(
    #       my_chain,
    #       data="my-dataset",
    #       evaluators=[GroundlensEvaluator()],
    #   )

    print("=== GroundlensEvaluator Demo ===\n")
    print("In production, use with LangSmith:\n")
    print("  from langsmith import evaluate as ls_evaluate")
    print("  results = ls_evaluate(")
    print("      my_chain,")
    print('      data="my-dataset",')
    print("      evaluators=[GroundlensEvaluator()],")
    print("  )\n")

    # Quick standalone test with mock objects.
    class MockRun:
        def __init__(self, output):
            self.outputs = {"output": output}

    class MockExample:
        def __init__(self, question, context=None):
            self.inputs = {"question": question}
            if context:
                self.inputs["context"] = context

    evaluator = GroundlensEvaluator()

    result = evaluator(
        MockRun("The speed of light is approximately 3 x 10^8 m/s."),
        MockExample(
            "What is the speed of light?",
            context="Light travels at 299,792,458 metres per second in vacuum.",
        ),
    )
    print(f"Key:     {result['key']}")
    print(f"Score:   {result['score']:.3f}")
    print(f"Comment: {result['comment']}")
