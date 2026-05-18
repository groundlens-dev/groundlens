# Changelog

All notable changes to groundlens are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
groundlens uses [Calendar Versioning](https://calver.org/) with the format `YYYY.M.D`.

## 2026.5.21 -- LangGraph integration fixes

### Fixed

- **LangGraph callback `on_chain_start` crash:** Guard against `serialized=None` parameter that some LangGraph chain types pass.
- **LangGraph context flow (all-DGI bug):** Retriever nodes produce context via chain state updates, not tool callbacks. Added node tracking via `_node_run_ids` and context capture in `on_chain_end` so subsequent LLM calls get SGI scoring.
- **Reporter SGI inflation:** Removed fallback context capture that was storing synthesizer output as reporter context, inflating SGI to meaningless values (5.8–10.0). Now only priority keys (`context`, `documents`, `retrieved_docs`, `search_results`) are captured.
- **Notebook render error:** Removed stale `metadata.widgets` from notebook JSON that caused "missing 'state' key" render failures.
- **Dallas retriever word matching:** Changed from substring match to all-words match so `"dallas_capital"` matches queries like "what is the capital of the state where dallas is located."

### Changed

- **Notebook restructure:** All installs and imports consolidated at the top. Clear API key setup instructions (HF_TOKEN + OPENAI_API_KEY) added at the beginning.

## 2026.4.22 -- Initial release

### Added

- **SGI (Semantic Grounding Index):** context-required hallucination detection via embedding distance ratios. Implements the method from arXiv:2512.13771.
- **DGI (Directional Grounding Index):** context-free hallucination detection via directional alignment with a calibrated reference direction. Implements the method from arXiv:2602.13224v3.
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
