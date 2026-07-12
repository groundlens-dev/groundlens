# CLAUDE.md — AI-assisted development guide for groundlens

This file provides context for AI coding agents (Claude Code, Copilot, Codex) working on the groundlens codebase. Read this before making changes.

## What is groundlens

A Python library that triages LLM outputs using embedding geometry, with no LLM in the scoring path. It is the deterministic **first stage** of a two-stage pipeline: it computes auditable scores from spatial relationships in sentence-transformer embedding spaces, and the second stage (an LLM judge or a human) runs only on what it escalates.

Two methods:
- **SGI** (Semantic Grounding Index): distance ratio, requires context. `dist(r, q) / dist(r, ctx)`.
- **DGI** (Directional Grounding Index): cosine alignment with calibrated reference direction, no context required.

The library is used in regulated environments (legal, healthcare, finance). Determinism and auditability are non-negotiable requirements.

## Critical constraints — do not violate

1. **Determinism is sacred.** Same inputs → same outputs, always. No randomness in scoring paths. No sampling. No stochastic operations. If you're tempted to add `random.seed()` anywhere, you're solving the wrong problem.

2. **No LLM in the scoring path.** groundlens is the deterministic first stage; it never uses an LLM to score. The second-stage judge or human is downstream, on escalations only. Never add LLM-based scoring, LLM-as-judge patterns, or inference calls in the scoring path.

3. **Frozen result types.** `SGIResult`, `DGIResult`, and `GroundlensScore` are frozen dataclasses (`frozen=True, slots=True`). Do not unfreeze them. Immutability is a design decision, not a convenience.

4. **`_internal/` is private.** Nothing outside `src/groundlens/` should import from `_internal/`. The public API is defined in `__init__.py`. Period.

5. **Lazy imports for optional deps.** Providers and integrations import their third-party dependencies inside function bodies, not at module level. `import groundlens` must never fail because `openai` isn't installed.

6. **Unit tests must not load the embedding model.** Tests in `tests/unit/` must run without downloading or loading `all-MiniLM-L6-v2`. Mock the encoder in unit tests. Integration tests in `tests/integration/` may load the model.

## Architecture

```
src/groundlens/
├── __init__.py              # Public API — all exports listed in __all__
├── _version.py              # CalVer: YYYY.M.D (e.g., 2026.4.22)
├── sgi.py                   # SGI scoring (compute_sgi, SGI class)
├── dgi.py                   # DGI scoring (compute_dgi, DGI class)
├── evaluate.py              # evaluate(), evaluate_batch() — auto-selects method
├── calibrate.py             # calibrate(), CalibrationResult
├── score.py                 # Result dataclasses with explanation logic
├── _internal/
│   ├── geometry.py          # Pure numpy: distances, normalization, cosine sim
│   ├── embeddings.py        # Model loading, caching, encode_texts()
│   ├── thresholds.py        # Decision boundaries and normalization functions
│   └── csv_loader.py        # Calibration CSV parsing
├── cli/
│   └── main.py              # CLI entry: check, evaluate, calibrate, benchmark, doctor
├── providers/               # Optional LLM provider wrappers
│   ├── _base.py             # BaseLLMProvider protocol + LLMResponse
│   ├── openai.py
│   ├── anthropic.py
│   └── google.py
└── integrations/            # Optional framework integrations
    ├── langchain/
    ├── crewai/
    ├── semantic_kernel/
    └── autogen/
```

## Development commands

```bash
# Install for development
pip install -e ".[dev]"
pre-commit install

# Run all tests
pytest

# Unit tests only (fast, no model download)
pytest tests/unit/

# Integration tests (loads model, slower)
pytest tests/integration/

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check (strict mode)
mypy src/groundlens/

# Build docs locally
pip install -e ".[docs]"
mkdocs serve
```

## Code style

- **Formatter/linter:** ruff, line-length 99, target Python 3.10
- **Type checking:** mypy strict mode — all public functions fully annotated
- **Docstrings:** Google style, enforced by ruff D rules
- **Tests:** pytest with `--strict-markers`. Mark slow tests with `@pytest.mark.slow`
- **Coverage:** target 85%+

## Where things live

| You want to... | Look at... |
|---|---|
| Change how SGI/DGI is calculated | `sgi.py`, `dgi.py` |
| Modify thresholds or normalization | `_internal/thresholds.py` |
| Change the embedding model default | `_internal/embeddings.py` → `DEFAULT_MODEL` |
| Add a new CLI subcommand | `cli/main.py` → add handler + parser |
| Add a new LLM provider | `providers/` → implement `BaseLLMProvider` |
| Add a new framework integration | `integrations/` → new subpackage |
| Update the version | `_version.py` (CalVer: YYYY.M.D) |
| Add a dependency | `pyproject.toml` → `dependencies` or `optional-dependencies` |
| Modify the public API | `__init__.py` → update `__all__` |

## Versioning

CalVer: `YYYY.M.D`. The version lives in `src/groundlens/_version.py` and in `pyproject.toml`. Both must match.

## Research context

groundlens implements methods from three papers:
1. SGI — arXiv:2512.13771 (Marin, 2025)
2. DGI + geometric taxonomy — arXiv:2602.13224v3 (Marin, 2026)
3. Confabulation benchmark — arXiv:2603.13259 (Marin, 2026)

If you're modifying SGI/DGI math, check the paper formulas. The code must match the published definitions.

## Common pitfalls

- **Don't normalize embeddings before SGI.** SGI uses raw Euclidean distances. L2-normalizing would collapse the distance ratio. `encode_texts()` returns raw encoder output intentionally.
- **Don't cache DGI reference directions globally.** The reference direction `mu_hat` depends on the calibration data. Different domains have different directions. The cache is per-model, not per-direction.
- **Don't add print statements in library code.** Use `logging.getLogger(__name__)`. The CLI is the only place where `print()` is acceptable (ruff T20 is suppressed there).
- **Don't break the CLI `--help` speed.** All heavy imports (sentence-transformers, numpy) are deferred in `cli/main.py`. Importing at the top level makes `groundlens --help` take 3+ seconds.
