"""groundlens REST API.

Lightweight HTTP wrapper around the groundlens library.
Deploy on Hugging Face Spaces (Docker SDK), Railway, Fly.io, or any container host.

Endpoints:
  POST /v1/check   — auto-selects SGI or DGI based on whether context is provided
  POST /v1/sgi     — explicit context-based grounding check
  POST /v1/dgi     — explicit context-free grounding check
  GET  /health     — liveness + model status
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────────────────────────────────────────────────────────
# Model preloading
# ─────────────────────────────────────────────────────────────────────────────

_model_ready = False
_model_load_time: float = 0.0


def _load_model() -> None:
    """Import groundlens to trigger model download + warm the embedding cache."""
    global _model_ready, _model_load_time  # noqa: PLW0603
    if _model_ready:
        return
    t0 = time.monotonic()
    from groundlens import compute_dgi

    # Warm up — first call loads the sentence-transformer model
    compute_dgi(question="warmup", response="warmup")
    _model_load_time = round(time.monotonic() - t0, 2)
    _model_ready = True


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Load model at startup so first request is fast."""
    _load_model()
    yield


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="groundlens API",
    description=(
        "LLM hallucination detection using embedding geometry. "
        "No second LLM. Deterministic. Same inputs → same scores."
    ),
    version="2026.5.12",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────────────────────────────────────


class CheckRequest(BaseModel):
    """Auto-select SGI or DGI based on whether context is provided."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(
        ...,
        description="The question asked to the LLM",
        min_length=1,
        max_length=10_000,
    )
    response: str = Field(
        ...,
        description="The LLM's response to evaluate",
        min_length=1,
        max_length=50_000,
    )
    context: str | None = Field(
        default=None,
        description=(
            "Source material (document, RAG chunks, reference text). "
            "If provided → SGI. If omitted → DGI."
        ),
        max_length=100_000,
    )


class SGIRequest(BaseModel):
    """Explicit context-based grounding check."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=1, max_length=10_000)
    context: str = Field(..., min_length=1, max_length=100_000)
    response: str = Field(..., min_length=1, max_length=50_000)


class DGIRequest(BaseModel):
    """Explicit context-free grounding check."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=1, max_length=10_000)
    response: str = Field(..., min_length=1, max_length=50_000)


class SGIDetail(BaseModel):
    """Detail fields for an SGI grounding result."""

    q_dist: float
    ctx_dist: float
    interpretation: str


class DGIDetail(BaseModel):
    """Detail fields for a DGI grounding result."""

    interpretation: str


class GroundingResult(BaseModel):
    """Structured response from a grounding check."""

    verdict: str = Field(description="GROUNDED or HALLUCINATION RISK")
    flagged: bool = Field(description="True if hallucination risk detected")
    method: str = Field(description="SGI or DGI")
    score: float = Field(description="Grounding score")
    threshold: float = Field(description="Score threshold for flagging")
    explanation: str = Field(description="Plain-language explanation")
    detail: SGIDetail | DGIDetail
    latency_ms: int = Field(description="Processing time in milliseconds")


class HealthResponse(BaseModel):
    """Health check response with model status."""

    status: str
    model_loaded: bool
    model_load_time_s: float
    version: str


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _run_sgi(question: str, context: str, response: str) -> GroundingResult:
    from groundlens import compute_sgi

    t0 = time.monotonic()
    result = compute_sgi(question=question, context=context, response=response)
    latency = int((time.monotonic() - t0) * 1000)

    return GroundingResult(
        verdict="GROUNDED" if not result.flagged else "HALLUCINATION RISK",
        flagged=result.flagged,
        method="SGI (Semantic Grounding Index)",
        score=round(result.value, 4),
        threshold=0.95,
        explanation=(
            "The response appears grounded in the source material."
            if not result.flagged
            else "The response may not be based on the source material provided."
        ),
        detail=SGIDetail(
            q_dist=round(result.q_dist, 4),
            ctx_dist=round(result.ctx_dist, 4),
            interpretation=result.explanation,
        ),
        latency_ms=latency,
    )


def _run_dgi(question: str, response: str) -> GroundingResult:
    from groundlens import compute_dgi

    t0 = time.monotonic()
    result = compute_dgi(question=question, response=response)
    latency = int((time.monotonic() - t0) * 1000)

    return GroundingResult(
        verdict="GROUNDED" if not result.flagged else "HALLUCINATION RISK",
        flagged=result.flagged,
        method="DGI (Directional Grounding Index)",
        score=round(result.value, 4),
        threshold=0.30,
        explanation=(
            "The response follows patterns typical of grounded answers."
            if not result.flagged
            else "The response shows geometric patterns associated with hallucination."
        ),
        detail=DGIDetail(
            interpretation=result.explanation,
        ),
        latency_ms=latency,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Liveness check. Returns model load status."""
    return HealthResponse(
        status="ok" if _model_ready else "loading",
        model_loaded=_model_ready,
        model_load_time_s=_model_load_time,
        version="2026.5.12",
    )


@app.post("/v1/check", response_model=GroundingResult, tags=["grounding"])
async def check(req: CheckRequest) -> GroundingResult:
    """Check whether an LLM response is hallucinated.

    Auto-selects the right method:
    - Context provided → SGI (checks if the response used the source material)
    - No context → DGI (checks geometric grounding patterns)
    """
    if not _model_ready:
        raise HTTPException(503, "Model is still loading. Try again in a few seconds.")

    has_context = req.context is not None and req.context.strip() != ""

    if has_context:
        return _run_sgi(req.question, req.context, req.response)
    return _run_dgi(req.question, req.response)


@app.post("/v1/sgi", response_model=GroundingResult, tags=["grounding"])
async def sgi(req: SGIRequest) -> GroundingResult:
    """SGI — check if the response is grounded in a source document.

    Use for RAG pipelines, document Q&A, or any case where you have
    the source material the LLM was given.
    """
    if not _model_ready:
        raise HTTPException(503, "Model is still loading. Try again in a few seconds.")

    return _run_sgi(req.question, req.context, req.response)


@app.post("/v1/dgi", response_model=GroundingResult, tags=["grounding"])
async def dgi(req: DGIRequest) -> GroundingResult:
    """DGI — check grounding patterns without source context.

    Use for open-ended chat, general Q&A, or any case where you just
    have a question and the LLM's answer.
    """
    if not _model_ready:
        raise HTTPException(503, "Model is still loading. Try again in a few seconds.")

    return _run_dgi(req.question, req.response)
