"""FastAPI REST server for Shadow Engineer. Multi-repo, async-safe.

Features: API key auth, Redis-backed rate limiting (fail-open),
LRU engine registry, versioned API.

Usage:
    uvicorn shadow_engine.api_server.server:app --reload
    curl http://localhost:8000/health
    curl http://localhost:8000/v1/health
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Depends, Security, APIRouter, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from ..main import ShadowEngine
from ..redis_limiter import RedisRateLimiter


# ── Rate Limiter (Redis-first with in-memory fallback) ───────────

_rate_limiter = RedisRateLimiter(
    redis_url=os.environ.get("SHADOW_ENGINE_REDIS_URL", "redis://localhost:6379"),
    max_requests=int(os.environ.get("SHADOW_ENGINE_RATE_LIMIT", "100")),
    window_seconds=int(os.environ.get("SHADOW_ENGINE_RATE_WINDOW", "60")),
)


# ── Auth ──────────────────────────────────────────────────────────

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_configured_api_key = os.environ.get("SHADOW_ENGINE_API_KEY") or None


async def verify_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> None:
    if _configured_api_key is not None:
        if api_key is None or api_key != _configured_api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Engine Registry ───────────────────────────────────────────────

class EngineRegistry:
    """Thread-safe LRU registry of ShadowEngine instances keyed by repo path."""

    def __init__(self, max_size: int = 32):
        self._max_size = max_size
        self._engines: dict[str, ShadowEngine] = {}
        self._access_order: list[str] = []
        self._lock = threading.Lock()

    def get(self, repo_path: str | Path = ".") -> ShadowEngine:
        key = str(Path(repo_path).resolve())
        with self._lock:
            if key in self._engines:
                self._access_order.remove(key)
                self._access_order.append(key)
                return self._engines[key]
            while len(self._engines) >= self._max_size and self._access_order:
                old_key = self._access_order.pop(0)
                old_engine = self._engines.pop(old_key, None)
                if old_engine:
                    old_engine.close()
            engine = ShadowEngine(storage_path=Path(key) / ".shadow-engine", repo_path=key)
            self._engines[key] = engine
            self._access_order.append(key)
            return engine

    def close_all(self) -> None:
        with self._lock:
            for engine in self._engines.values():
                engine.close()
            self._engines.clear()
            self._access_order.clear()


_registry = EngineRegistry(max_size=32)


def get_engine(repo: str = Query(".", description="Repository path")) -> ShadowEngine:
    return _registry.get(repo)


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Shadow Engineer API",
    description="Self-improving background agent with persistent knowledge graph and parallel experimentation",
    version="1.0.0",
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Any):
    """Rate limit every API request. Health check is exempt."""
    if request.url.path.endswith("/health"):
        return await call_next(request)
    client_id = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(client_id):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again shortly."})
    return await call_next(request)


# ── Response Models ───────────────────────────────────────────────

class BootstrapResponse(BaseModel):
    status: str; repository: str; symbols_indexed: int; files_indexed: int; semantic_search: bool
class ContextResponse(BaseModel):
    context: str
class SearchResponse(BaseModel):
    results: list[dict[str, Any]]; total: int
class ImpactResponse(BaseModel):
    symbol: dict[str, Any]; impact_radius: list[str]; total_affected_symbols: int
class SuggestResponse(BaseModel):
    problem_type: str; classification_confidence: float; recommended_approach: str; expected_success_rate: float; best_model: str; confidence: float
class SessionResult(BaseModel):
    session_id: str; outcome: str; prompt: str; approach: str = ""; model: str = "default"
    pr_url: str | None = None; files_changed: list[str] = []; tests_passed: int = 0
    tests_failed: int = 0; review_comments: list[str] = []; duration_seconds: float = 0.0; token_count: int = 0
class IngestResponse(BaseModel):
    status: str; problem_type: str; classification_confidence: float; was_successful: bool; patterns_learned: int
class StatsResponse(BaseModel):
    total_symbols: int; total_files: int; total_sessions: int; successful_sessions: int; overall_success_rate: float


# ── Routes (Fix #1: Single router, mounted at root AND /v1 — zero duplication) ──

router = APIRouter()


@router.post("/bootstrap", response_model=BootstrapResponse)
async def bootstrap(repo: str = Query("."), _: None = Depends(verify_api_key)):
    result = _registry.get(repo).bootstrap()
    return BootstrapResponse(**result)


@router.get("/context", response_model=ContextResponse)
async def get_context(task: str = Query(...), engine: ShadowEngine = Depends(get_engine), _: None = Depends(verify_api_key)):
    return ContextResponse(context=engine.get_context(task))


@router.get("/search", response_model=SearchResponse)
async def search(query: str = Query(...), kind: str | None = Query(None), engine: ShadowEngine = Depends(get_engine), _: None = Depends(verify_api_key)):
    results = engine.search(query, kind=kind)
    return SearchResponse(results=results, total=len(results))


@router.get("/impact/{symbol_name}", response_model=ImpactResponse)
async def impact(symbol_name: str, engine: ShadowEngine = Depends(get_engine), _: None = Depends(verify_api_key)):
    result = engine.impact(symbol_name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return ImpactResponse(**result)


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(task: str = Query(...), engine: ShadowEngine = Depends(get_engine), _: None = Depends(verify_api_key)):
    r = engine.suggest(task)
    return SuggestResponse(problem_type=r["problem_type"], classification_confidence=r.get("classification_confidence", 0.0), recommended_approach=r["recommended_approach"], expected_success_rate=r.get("expected_success_rate", 0.0), best_model=r.get("best_model", "unknown"), confidence=r["confidence"])


@router.post("/experiment")
async def experiment(task: str = Query(...), variants: int = Query(3, ge=1, le=10), engine: ShadowEngine = Depends(get_engine), _: None = Depends(verify_api_key)):
    return engine.experiment(task, num_variants=variants)


@router.post("/sessions/ingest", response_model=IngestResponse)
async def ingest_session(result: SessionResult, engine: ShadowEngine = Depends(get_engine), _: None = Depends(verify_api_key)):
    ingestion = engine.record_result(session_id=result.session_id, outcome=result.outcome, prompt=result.prompt, approach=result.approach, model=result.model, pr_url=result.pr_url, files_changed=result.files_changed, test_results={"total": result.tests_passed + result.tests_failed, "passed": result.tests_passed, "failed": result.tests_failed}, review_comments=result.review_comments, duration_seconds=result.duration_seconds, token_count=result.token_count)
    return IngestResponse(status=ingestion["status"], problem_type=ingestion["problem_type"], classification_confidence=ingestion.get("classification_confidence", 0.0), was_successful=ingestion["was_successful"], patterns_learned=len(ingestion.get("patterns_learned", [])))


@router.get("/report")
async def report(engine: ShadowEngine = Depends(get_engine), _: None = Depends(verify_api_key)):
    return PlainTextResponse(content=engine.get_report())


@router.get("/stats", response_model=StatsResponse)
async def stats(engine: ShadowEngine = Depends(get_engine), _: None = Depends(verify_api_key)):
    s = engine.get_stats()
    return StatsResponse(**s)


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat(), "version": "1.0.0"}


@router.get("/metrics")
async def metrics(engine: ShadowEngine = Depends(get_engine), _: None = Depends(verify_api_key)):
    return engine.get_metrics()


# Fix #1: Include same router at root AND /v1 — zero code duplication
app.include_router(router)
app.include_router(router, prefix="/v1")