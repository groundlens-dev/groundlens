"""Second stage (groundlens.verify): escalate only what geometry cannot settle.

Run:
    pip install "groundlens[verify]"
    python examples/second_stage.py

Needs a GPU for the local model. To use an API model instead, wrap your client
in an object exposing ``generate(prompt, n) -> list[str]`` and pass it as
``generator=...`` (see the TextGenerator protocol in groundlens.verify).
"""

from __future__ import annotations

from groundlens.verify import SelfCheckNLI, two_stage

MODEL = "Qwen/Qwen2.5-7B-Instruct"


def main() -> None:
    # 1) The pipeline: stage 1 (deterministic) gates stage 2 (model-based).
    grounded = two_stage(
        question="What is the capital of Spain?",
        answer="Madrid",
        context="Spain is a country in Europe. Its capital is Madrid.",
        model=MODEL,
    )
    print("grounded case  -> escalated:", grounded.escalated)
    print(grounded.final)  # SGI settled it; no model call was made
    print()

    # 2) A case with no source: DGI may escalate, and stage 2 then runs.
    checker = SelfCheckNLI(model=MODEL, n_samples=7)  # reuse one loaded model
    unsourced = two_stage(
        question="Who won the 1997 Nobel Prize in Literature?",
        answer="Dario Fo",
        detector=checker,
    )
    print("unsourced case -> escalated:", unsourced.escalated)
    print(unsourced.final)
    if unsourced.stage2 is not None:
        print("consistency:", round(unsourced.stage2.consistency, 3),
              "| samples:", list(unsourced.stage2.samples))

    # 3) Call the second stage directly (no first stage) when you want it.
    reading = checker.verify("What is the boiling point of water at sea level?", "100 C")
    print()
    print("direct check   ->", reading.check.level, "|", reading.method,
          "|", round(reading.seconds, 2), "s")


if __name__ == "__main__":
    main()
