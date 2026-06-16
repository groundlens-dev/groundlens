"""Confabulation strategy prompt templates for active-learning bootstrap.

Five strategies derived from the human-confabulation taxonomy reported in:

    Marin, J. (2026). A Methodology for Building Human-Confabulated
    Hallucination Benchmarks. groundlens-dev/grounding-benchmark.

Each strategy preserves a different subset of the distributional
properties that embedding models encode while violating referential
truth. Together they sample the four observed failure modes of
embedding-based hallucination detectors (within-register
confabulations, mechanism-level reversals, entity composition,
polysemic reinterpretation, and template-preserving substitutions).

The templates take three slots:

- ``{context}``  -- an excerpt from the deployment's FAQ corpus
- ``{question}`` -- a question consistent with the context
- ``{grounded}`` -- the verified-grounded response to the question

and produce a prompt that an arbitrary text-generation LLM can answer
with a *confabulated* response written in the same register as the
grounded one.

Public API
----------

Strategies are referenced by name (string). The defaults are::

    DEFAULT_STRATEGIES = (
        "redefinition",
        "mechanism_inversion",
        "entity_composition",
        "polysemy",
        "template_filling",
    )

A caller can pass a subset of these names to
``DGI.propose_labels(..., strategies=(...))``, or a tuple of custom
``(name, prompt_template)`` pairs::

    strategies = (
        ("my_strategy", "Generate a wrong response that ... {context} ... {grounded}"),
    )
"""

from __future__ import annotations

DEFAULT_STRATEGIES: tuple[str, ...] = (
    "redefinition",
    "mechanism_inversion",
    "entity_composition",
    "polysemy",
    "template_filling",
)

_TEMPLATES: dict[str, str] = {
    "redefinition": (
        "Read the following grounded response and write a confabulated alternative "
        "that REDEFINES one of its key terms while keeping the same vocabulary, "
        "register, and sentence structure. The redefinition must be plausible to a "
        "non-expert but factually wrong.\n\n"
        "Context (from the deployment's FAQ): {context}\n\n"
        "Question: {question}\n\n"
        "Grounded response: {grounded}\n\n"
        "Confabulated response (one paragraph, same register, redefining a key term):"
    ),
    "mechanism_inversion": (
        "Read the following grounded response and write a confabulated alternative "
        "that REVERSES the underlying mechanism or causal direction while preserving "
        "the local sentence transitions (so each sub-clause sounds plausible in "
        "isolation). The global meaning must be wrong.\n\n"
        "Context: {context}\n\n"
        "Question: {question}\n\n"
        "Grounded response: {grounded}\n\n"
        "Confabulated response (inverted mechanism, same register):"
    ),
    "entity_composition": (
        "Read the following grounded response and write a confabulated alternative "
        "that COMBINES real entities (institutions, procedures, products, agencies) "
        "into a fictitious mechanism. Every entity named must be real; their "
        "composition must be invented.\n\n"
        "Context: {context}\n\n"
        "Question: {question}\n\n"
        "Grounded response: {grounded}\n\n"
        "Confabulated response (real entities, invented composition):"
    ),
    "polysemy": (
        "Read the following grounded response and write a confabulated alternative "
        "that EXPLOITS a polysemic or ambiguous term: pick a word with multiple "
        "senses, shift the response to the wrong sense, and provide supporting "
        "context that consistently reinforces the wrong interpretation.\n\n"
        "Context: {context}\n\n"
        "Question: {question}\n\n"
        "Grounded response: {grounded}\n\n"
        "Confabulated response (wrong sense of a polysemic term, with consistent "
        "supporting context):"
    ),
    "template_filling": (
        "Read the following grounded response and write a confabulated alternative "
        "that PRESERVES the discourse structure (introduction, claim, justification, "
        "qualifier) while REPLACING every concrete fact (numbers, names, dates, "
        "thresholds) with plausible-but-wrong substitutes.\n\n"
        "Context: {context}\n\n"
        "Question: {question}\n\n"
        "Grounded response: {grounded}\n\n"
        "Confabulated response (same discourse template, wrong facts):"
    ),
}


def get_template(strategy: str) -> str:
    """Return the prompt template for a named built-in strategy.

    Raises:
        KeyError: if ``strategy`` is not one of :data:`DEFAULT_STRATEGIES`.
    """
    if strategy not in _TEMPLATES:
        msg = (
            f"Unknown strategy {strategy!r}. "
            f"Built-in strategies: {DEFAULT_STRATEGIES}. "
            f"Pass a tuple of (name, prompt_template) pairs to use a custom strategy."
        )
        raise KeyError(msg)
    return _TEMPLATES[strategy]


def resolve_strategies(
    strategies: str | tuple[str | tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """Resolve a ``strategies`` argument into a tuple of (name, template).

    Accepts:
    - the string ``"default"`` (returns all five built-in strategies);
    - a tuple of built-in strategy names, e.g. ``("redefinition", "polysemy")``;
    - a tuple of ``(name, prompt_template)`` pairs (custom strategies);
    - a mix: tuple entries that are strings are looked up in the built-ins,
      tuple entries that are ``(name, template)`` are used verbatim.

    Returns:
        Tuple of ``(name, template)`` pairs, in the order supplied.

    Raises:
        TypeError: if ``strategies`` is neither a string nor a tuple.
        KeyError: if a string entry is not a built-in strategy.
        ValueError: if a non-string entry is not a 2-tuple of strings.
    """
    if isinstance(strategies, str):
        if strategies == "default":
            return tuple((name, _TEMPLATES[name]) for name in DEFAULT_STRATEGIES)
        # Single strategy name as a string.
        return ((strategies, get_template(strategies)),)

    if not isinstance(strategies, tuple):
        msg = f"strategies must be a string or tuple, got {type(strategies).__name__}."
        raise TypeError(msg)

    resolved: list[tuple[str, str]] = []
    for entry in strategies:
        if isinstance(entry, str):
            resolved.append((entry, get_template(entry)))
        elif (
            isinstance(entry, tuple)
            and len(entry) == 2
            and isinstance(entry[0], str)
            and isinstance(entry[1], str)
        ):
            resolved.append(entry)
        else:
            msg = (
                f"Invalid strategy entry: {entry!r}. "
                f"Each entry must be either a built-in strategy name (string) or "
                f"a (name, prompt_template) 2-tuple of strings."
            )
            raise ValueError(msg)
    return tuple(resolved)
