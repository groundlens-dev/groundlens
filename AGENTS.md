# AGENTS.md -- Codebase guide for AI coding agents

This file helps AI coding agents (Claude Code, Codex, Copilot Workspace, etc.) navigate and contribute to the groundlens codebase.

## What groundlens does

groundlens triages LLM outputs using embedding geometry. It computes deterministic scores from spatial relationships in an embedding space (default: `sentence-transformers/sentence-t5-large`, 768 dims, ~640MB --- the encoder the shipped thresholds and DGI `mu_hat` were calibrated on), with no LLM in the scoring path. It is the first stage of a two-stage pipeline; the second-stage judge or human runs only on what it escalates.

**Scope rules for every claim in this repo.** SGI is not DGI: SGI scores against a supplied source, DGI is reference-free, and the authorship control was run on DGI and on probes over embeddings, **not** on SGI. TruthfulQA AUC 0.478 is an SGI result; TruthfulQA 0.897 is a DGI result. The ~0.68 ceiling is measured for DGI and for logistic/MLP probes over those embeddings, not demonstrated for every embedding-similarity method — random forest and XGBoost retain residual signal up to 0.88 at high register alignment. Register sufficiency is an assumption, not a theorem, and only partially true: residual surface features retain partial Spearman up to 0.37 once register alignment is controlled. The formal bound covers only detectors that are functions of a single frozen sentence embedding — not activations, not log-probabilities, not multi-sample methods, not retrieval.

**House rule, non-negotiable: no benchmark number ships without the authorship and length controls.** Detectors that appear to beat the register wall are usually reading *who wrote the text*, not whether it is grounded. Before any AUROC, accuracy or detection rate enters a docstring, the README, the docs or a slide: hold authorship constant, match length, and report the per-register-bin curve rather than a pooled figure. A reported 0.9+ in this class is a signal to go looking for a shortcut, not a signal of quality. If a number has not been through the controls, label it "pending controls" or do not ship it.

Two scoring methods:
- **SGI (Semantic Grounding Index):** ratio-based, requires context. `SGI = theta(response, question) / theta(response, context)` where `theta(a, b) = arccos(a_hat . b_hat)` is the **angular** (geodesic) distance on the unit hypersphere, not the Euclidean distance.
- **DGI (Directional Grounding Index):** direction-based, context-free. `DGI = dot(normalize(delta), mu_hat)` where `delta = phi(response) - phi(question)`.

## Repository layout

```
groundlens/
├── src/groundlens/                # Source code (src layout)
│   ├── __init__.py              # Public API exports
│   ├── _version.py              # CalVer version string
│   ├── sgi.py                   # SGI: compute_sgi(), SGI class
│   ├── dgi.py                   # DGI: compute_dgi(), DGI class, calibration cache
│   ├── evaluate.py              # evaluate(), evaluate_batch() -- auto-selects method
│   ├── calibrate.py             # calibrate(), CalibrationResult
│   ├── score.py                 # Result dataclasses: SGIResult, DGIResult, GroundlensScore
│   ├── _internal/               # Private implementation (not public API)
│   │   ├── geometry.py          # euclidean_distance, displacement_vector, unit_normalize, cosine_similarity
│   │   ├── embeddings.py        # encode_texts(), model loading, DEFAULT_MODEL constant
│   │   ├── thresholds.py        # SGI_REVIEW, SGI_STRONG_PASS, DGI_PASS, normalization functions
│   │   └── csv_loader.py        # load_reference_pairs() for calibration data
│   ├── cli/
│   │   └── main.py              # CLI entry point: check, evaluate, calibrate, benchmark, doctor
│   ├── providers/               # LLM provider wrappers (optional deps)
│   │   ├── _base.py             # BaseLLMProvider protocol, LLMResponse dataclass
│   │   ├── openai.py            # OpenAI provider
│   │   ├── anthropic.py         # Anthropic provider
│   │   └── google.py            # Google Generative AI provider
│   └── integrations/            # Framework integrations (optional deps)
│       ├── langchain/           # Evaluator + callback handler
│       ├── crewai/              # CrewAI tool
│       ├── semantic_kernel/     # Semantic Kernel filter
│       └── autogen/             # AutoGen checker
├── tests/
│   ├── conftest.py              # Shared fixtures
│   ├── unit/                    # Unit tests (geometry, thresholds, score, csv_loader)
│   ├── integration/             # Integration tests (sgi, dgi, evaluate -- load model)
│   ├── providers/               # Provider tests (openai, anthropic, google)
│   └── integrations/            # Integration framework tests
├── examples/                    # Usage examples
├── benchmarks/                  # Performance and accuracy benchmarks
├── docs/                        # Documentation source (mkdocs-material)
├── pyproject.toml               # Build config (hatchling), deps, tool config
└── .pre-commit-config.yaml      # Pre-commit hooks
```

## Public API

All public symbols are exported from `groundlens/__init__.py`:

```python
from groundlens import compute_sgi, compute_dgi, evaluate, evaluate_batch, calibrate
from groundlens import SGI, DGI, SGIResult, DGIResult, GroundlensScore, CalibrationResult
```

## Key abstractions

### Result types (score.py)

- `SGIResult` -- frozen dataclass with `value`, `normalized`, `flagged`, `q_dist`, `ctx_dist`, `method`, `explanation`
- `DGIResult` -- frozen dataclass with `value`, `normalized`, `flagged`, `method`, `explanation`
- `GroundlensScore` -- unified wrapper returned by `evaluate()`, contains a `detail` field with the underlying SGI/DGI result

### Geometry layer (_internal/geometry.py)

Pure numpy operations: `euclidean_distance`, `unit_normalize`, `displacement_vector`, `cosine_similarity`, `mean_direction`. All operate on `NDArray[np.float32]` vectors.

### Thresholds (_internal/thresholds.py)

Decision boundaries: `SGI_REVIEW=0.95`, `SGI_STRONG_PASS=1.20`, `DGI_PASS=0.525`. SGI has three bands; DGI is a **single binary cut**. Normalization functions: `normalize_sgi()` (tanh, display-only) and `normalize_dgi()` (linear). **Never restate a threshold as a literal** --- import it from `groundlens._internal.thresholds`. Every stale copy of a cut-point in this repo has been a copied literal.

### Provider protocol (providers/_base.py)

`BaseLLMProvider` is a `Protocol` with `complete()` and `chat()` methods. `LLMResponse` carries `text`, `model`, `usage`, and optional `groundlens_score`.

## Commands

### Run tests

```bash
# All tests
pytest

# Unit tests only (fast, no model loading)
pytest tests/unit/

# Integration tests (loads sentence-transformers model)
pytest tests/integration/

# With coverage
pytest --cov=groundlens --cov-report=term-missing

# Skip slow tests
pytest -m "not slow"
```

### Lint and format

```bash
# Lint
ruff check src/ tests/

# Auto-fix
ruff check --fix src/ tests/

# Format
ruff format src/ tests/
```

### Type check

```bash
mypy src/groundlens/
```

mypy is configured in strict mode in `pyproject.toml`. Provider and integration dependencies use `ignore_missing_imports = true`.

### CLI

```bash
# Diagnose environment
groundlens doctor

# Single check
groundlens check --question "Q?" --response "A." --context "Source."

# Batch CSV
groundlens evaluate input.csv --output results.csv

# Calibrate DGI
groundlens calibrate --pairs pairs.csv --output calibration.json

# Benchmark
groundlens benchmark --dataset cert-framework/human-confabulation-benchmark
```

### Install for development

```bash
pip install -e ".[dev]"
pre-commit install
```

## Architecture principles

1. **src layout** -- source code lives in `src/groundlens/`, preventing accidental imports from the working directory.
2. **Private internals** -- `_internal/` is not part of the public API. Do not import from it in user-facing code outside the package.
3. **Lazy provider imports** -- providers and integrations are optional. They import their third-party dependencies at call time, not at package import time.
4. **Frozen dataclasses** -- all result types are immutable (`frozen=True, slots=True`).
5. **CalVer versioning** -- version format is `YYYY.M.D` in `_version.py`.
6. **Deferred CLI imports** -- the CLI defers all heavy imports to keep `groundlens --help` fast.

## Coding standards

- **Formatter/linter:** ruff (line-length 99, target Python 3.10)
- **Type checking:** mypy strict mode
- **Docstrings:** Google style (enforced by ruff D rules)
- **Tests:** pytest with strict markers. Tests in `tests/unit/` must not load the embedding model.
- **Coverage:** minimum 85% (configured in pyproject.toml)

## Common tasks for agents

### Adding a new provider

1. Create `src/groundlens/providers/new_provider.py`
2. Implement `BaseLLMProvider` protocol (see `_base.py`)
3. Add optional dependency in `pyproject.toml` under `[project.optional-dependencies]`
4. Add tests in `tests/providers/test_new_provider.py`
5. Add example in `examples/`

### Adding a new integration

1. Create `src/groundlens/integrations/new_framework/` with `__init__.py`
2. Import the framework dependency lazily
3. Add optional dependency in `pyproject.toml`
4. Add tests in `tests/integrations/test_new_framework.py`

### Modifying thresholds

Thresholds live in `src/groundlens/_internal/thresholds.py`. Changes require updating:
- The threshold constants
- The normalization function docstrings (reference point tables)
- The `score.py` explanation logic in `__post_init__`
- Tests in `tests/unit/test_thresholds.py`

### Updating the version

Edit `src/groundlens/_version.py`. The version follows CalVer: `YYYY.M.D`.
