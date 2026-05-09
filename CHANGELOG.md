# Changelog

All notable changes to groundlens are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
groundlens uses [Calendar Versioning](https://calver.org/) with the format `YYYY.M.D`.

## 2026.4.22 -- Initial release

### Added

- **SGI (Semantic Grounding Index):** context-required hallucination detection via embedding distance ratios. Implements the method from arXiv:2512.13771.
- **DGI (Directional Grounding Index):** context-free hallucination detection via directional alignment with a calibrated reference direction. Implements the method from arXiv:2602.13224.
- **`evaluate()` and `evaluate_batch()`:** high-level API that auto-selects SGI (when context is provided) or DGI (when context is absent).
- **Domain calibration:** `calibrate()` function and `CalibrationResult` for computing domain-specific DGI reference directions. 20-100 verified pairs improve AUROC from ~0.76 to 0.90-0.99.
- **Result types:** `SGIResult`, `DGIResult`, and `GroundlensScore` frozen dataclasses with scores, flags, and human-readable explanations.
- **CLI:** `groundlens check`, `groundlens evaluate`, `groundlens calibrate`, `groundlens benchmark` commands.
- **LLM providers:** OpenAI, Anthropic, and Google Generative AI wrappers with automatic hallucination scoring on every response.
- **Framework integrations:** LangChain evaluator and callback, CrewAI tool, Semantic Kernel filter, AutoGen checker.
- **Geometry layer:** Euclidean distance, displacement vectors, unit normalization, cosine similarity, and mean direction computation.
- **Threshold system:** Empirically derived decision boundaries with tanh (SGI) and linear (DGI) normalization to [0, 1].
- **Default model:** `all-MiniLM-L6-v2` (sentence-transformers). No GPU required.
- **Full type coverage:** mypy strict mode, all public APIs fully annotated.
- **Test suite:** unit tests (no model loading), integration tests, provider tests, and integration framework tests.
