# API Reference

This page provides the complete API reference for groundlens. All public classes and functions are documented with their signatures, parameters, return types, and examples.

For auto-generated documentation from source docstrings, ensure `mkdocstrings` is configured in your MkDocs build.

## Core Functions

### compute_sgi

::: groundlens.sgi.compute_sgi

### compute_dgi

::: groundlens.dgi.compute_dgi

### evaluate

::: groundlens.evaluate.evaluate

### evaluate_batch

::: groundlens.evaluate.evaluate_batch

### calibrate

::: groundlens.calibrate.calibrate

### fit_thresholds

::: groundlens.calibrate.fit_thresholds

### set_default_encoder

::: groundlens._internal.embeddings.set_default_encoder

### get_default_encoder

::: groundlens._internal.embeddings.get_default_encoder

## Core Classes

### SGI

::: groundlens.sgi.SGI

### DGI

::: groundlens.dgi.DGI

## Result Types

### SGIResult

::: groundlens.score.SGIResult

### DGIResult

::: groundlens.score.DGIResult

### GroundlensScore

::: groundlens.score.GroundlensScore

### CalibrationResult

::: groundlens.calibrate.CalibrationResult

### ThresholdFit

::: groundlens.calibrate.ThresholdFit

## Providers

### GroundlensOpenAI

::: groundlens.providers.openai.GroundlensOpenAI

### GroundlensAnthropic

::: groundlens.providers.anthropic.GroundlensAnthropic

### GroundlensGemini

::: groundlens.providers.google.GroundlensGemini

## Integrations

### GroundlensEvaluator (LangChain)

::: groundlens.integrations.langchain.evaluator.GroundlensEvaluator

### GroundlensCallback (LangChain)

::: groundlens.integrations.langchain.callback.GroundlensCallback

### GroundlensTool (CrewAI)

::: groundlens.integrations.crewai.tool.GroundlensTool

### GroundlensFilter (Semantic Kernel)

::: groundlens.integrations.semantic_kernel.filter.GroundlensFilter

### GroundlensChecker (AutoGen)

::: groundlens.integrations.autogen.checker.GroundlensChecker

## Internal Modules

!!! note "Internal API"
    The following modules are internal implementation details. They are documented here for completeness but are not part of the public API and may change without notice.

### Geometry Primitives

::: groundlens._internal.geometry

### Thresholds

::: groundlens._internal.thresholds

## Constants

| Constant | Value | Module | Description |
|---|---|---|---|
| `SGI_STRONG_PASS` | 1.20 | `groundlens._internal.thresholds` | SGI strong pass threshold |
| `SGI_REVIEW` | 0.95 | `groundlens._internal.thresholds` | SGI review/flag threshold |
| `DGI_PASS` | 0.30 | `groundlens._internal.thresholds` | DGI pass threshold |
| `DEFAULT_MODEL` | `"all-MiniLM-L6-v2"` | `groundlens._internal.embeddings` | Default sentence-transformer model |

## Type Summary

| Type | Description | Key fields |
|---|---|---|
| `SGIResult` | SGI computation result | `value`, `normalized`, `flagged`, `q_dist`, `ctx_dist` |
| `DGIResult` | DGI computation result | `value`, `normalized`, `flagged` |
| `GroundlensScore` | Unified evaluation result | `value`, `normalized`, `flagged`, `method`, `explanation`, `detail` |
| `CalibrationResult` | DGI calibration output | `model`, `n_pairs`, `embedding_dim`, `mu_hat`, `concentration` |
| `ThresholdFit` | Fitted SGI/DGI thresholds | `sgi_review`, `dgi_pass`, `n`, `model`, `metric` |
| `EmbeddingFn` | Bring-your-own encoder callable type | `Callable[[list[str]], NDArray[np.float32]]` |
| `LLMResponse` | Provider response wrapper | `text`, `model`, `usage`, `groundlens_score` |
