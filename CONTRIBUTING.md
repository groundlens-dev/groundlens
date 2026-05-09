# Contributing to groundlens

Thank you for your interest in contributing to groundlens. This document covers the development setup, code standards, and process for submitting changes.

## Prerequisites

- Python 3.10 or later
- Git
- A working knowledge of embedding geometry is helpful but not required for most contributions

## Development setup

1. Clone the repository:

```bash
git clone https://github.com/groundlens-dev/groundlens.git
cd groundlens
```

2. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

3. Install in editable mode with dev dependencies:

```bash
pip install -e ".[dev]"
```

4. Install pre-commit hooks:

```bash
pre-commit install
```

5. Verify the setup:

```bash
pytest tests/unit/          # Fast tests (no model loading)
ruff check src/ tests/      # Lint
mypy src/groundlens/          # Type check
```

## Code standards

### Formatting and linting

We use [ruff](https://docs.astral.sh/ruff/) for both linting and formatting:

```bash
# Check for issues
ruff check src/ tests/

# Auto-fix what can be fixed
ruff check --fix src/ tests/

# Format code
ruff format src/ tests/
```

Configuration is in `pyproject.toml`. Key settings:
- Line length: 99
- Target: Python 3.10
- Docstring convention: Google style
- Tests and examples have relaxed rules (no docstring or annotation requirements)

### Type checking

mypy runs in strict mode:

```bash
mypy src/groundlens/
```

All public functions must have complete type annotations. Use `from __future__ import annotations` at the top of every module.

### Testing

We use pytest with strict markers:

```bash
# All tests
pytest

# Unit tests only (no model loading, fast)
pytest tests/unit/

# Integration tests (loads sentence-transformers model)
pytest tests/integration/

# Provider tests
pytest tests/providers/

# Integration framework tests
pytest tests/integrations/

# With coverage report
pytest --cov=groundlens --cov-report=term-missing
```

Coverage minimum is 85%. New code should include tests. Tests go in the corresponding directory under `tests/`:

| Source | Test location |
|---|---|
| `src/groundlens/sgi.py` | `tests/integration/test_sgi.py` |
| `src/groundlens/_internal/geometry.py` | `tests/unit/test_geometry.py` |
| `src/groundlens/providers/openai.py` | `tests/providers/test_openai.py` |
| `src/groundlens/integrations/langchain/` | `tests/integrations/test_langchain.py` |

Unit tests in `tests/unit/` must not load the embedding model. Use mocking or pre-computed values.

### Docstrings

Every public function, class, and method needs a Google-style docstring:

```python
def compute_sgi(
    question: str,
    context: str,
    response: str,
    *,
    model: str = DEFAULT_MODEL,
) -> SGIResult:
    """Compute the Semantic Grounding Index for a response.

    Args:
        question: The input query.
        context: Source document, retrieved chunks, or reference text.
        response: The LLM output to evaluate.
        model: Sentence transformer model name.

    Returns:
        SGIResult with raw score, normalized score, and flag status.

    Raises:
        ValueError: If any input string is empty.
    """
```

## Commit conventions

Use conventional commit prefixes:

- `feat:` -- new feature
- `fix:` -- bug fix
- `docs:` -- documentation changes
- `test:` -- adding or updating tests
- `refactor:` -- code restructuring without behavior change
- `perf:` -- performance improvement
- `ci:` -- CI/CD changes
- `chore:` -- maintenance tasks

Examples:

```
feat: add cosine distance option to SGI computation
fix: handle empty context string in evaluate()
docs: add domain calibration example to README
test: add edge case tests for degenerate displacement vectors
```

## Pull request process

1. **Fork and branch.** Create a feature branch from `main`:

```bash
git checkout -b feat/my-feature main
```

2. **Make your changes.** Follow the code standards above.

3. **Test locally.** All of these must pass:

```bash
pytest
ruff check src/ tests/
mypy src/groundlens/
```

4. **Push and open a PR.** Target the `main` branch. Fill in the PR template.

5. **Review.** All PRs require at least one approval. We may ask for changes. This is normal and constructive.

6. **Merge.** After approval, the maintainer will merge via squash-and-merge.

### PR checklist

- [ ] Tests pass locally (`pytest`)
- [ ] Linting passes (`ruff check src/ tests/`)
- [ ] Type checking passes (`mypy src/groundlens/`)
- [ ] New code has tests
- [ ] New public API has docstrings
- [ ] CHANGELOG.md updated (for user-facing changes)

## What to contribute

Good first contributions:

- **Documentation improvements.** Typos, unclear explanations, missing examples.
- **Test coverage.** Edge cases, error paths, provider mocking.
- **Examples.** New usage examples in `examples/`.
- **Bug reports.** Clear reproduction steps help enormously.

Larger contributions (please open an issue to discuss first):

- New scoring methods or geometric primitives
- New LLM provider integrations
- New framework integrations
- Changes to thresholds or normalization functions
- Performance optimizations in the embedding pipeline

## Questions?

Open a [discussion](https://github.com/groundlens-dev/groundlens/discussions) or email javier@jmarin.info.
