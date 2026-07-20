import asyncio
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.auth import AuthMiddleware
from src.api.routes_admin import admin_api_router, admin_base_router
from src.api.routes_chat import chat_router, export_router
from src.api.state import (
    APP_VERSION,
    get_startup_seconds,
    probe,
    probe_embed,
    probe_ollama,
    probe_qdrant,
    set_dag_engine,
    set_metrics_store,
    set_registry,
    set_session_store,
    set_startup_seconds,
)
from src.config import get_app_config, load_app_config, register_reload_callback, reload_app_config
from src.engine import DAGEngine, ToolRegistry
from src.engine.tools import (
    api_call,
    code,
    db_query,
    extract_llm,
    extract_regex,
    llm_tool,
    rag_search,
    router,
    web_search,
)
from src.logger import get_logger, init_logging
from src.logger.middleware import RequestIDMiddleware, get_request_id
from src.metrics.factory import create_metrics_store
from src.metrics.prometheus import MetricsMiddleware, generate_latest
from src.session import MemorySessionStore, SessionStore

_log = get_logger(__name__)

# ---- lifecycle ----

_START_TIME = time.time()
_startup_seconds: float | None = None

_startup_sync_oss = bool(os.environ.get("OSS_ACCESS_KEY_ID"))
_app_config = load_app_config(sync_oss=_startup_sync_oss)
init_logging(_app_config.logging.level, app_name="fastapi")

if _app_config.db:
    from src.db import create_pool

    for name, pool_cfg in _app_config.db.pools.items():
        create_pool(name, pool_cfg)

_metrics_store = create_metrics_store(getattr(_app_config, "metrics", None))
set_metrics_store(_metrics_store)
_registry = ToolRegistry()
_registry.register("llm", llm_tool)
_registry.register("rag_search", rag_search)
_registry.register("router", router)
_registry.register("db_query", db_query)
_registry.register("extract_llm", extract_llm)
_registry.register("extract_regex", extract_regex)
_registry.register("api_call", api_call)
_registry.register("web_search", web_search)
_registry.register("code", code)
set_registry(_registry)
_dag_engine = DAGEngine(
    tools=_registry, app_config=_app_config, metrics_store=_metrics_store,
)
set_dag_engine(_dag_engine)
register_reload_callback(lambda cfg: _dag_engine.update_app_config(cfg))

_session_store: SessionStore = MemorySessionStore(
    max_age=getattr(_app_config.session, "max_age", 3600),
    max_sessions=getattr(_app_config.session, "memory_max_sessions", 2000),
)
set_session_store(_session_store)

_cleanup_event = threading.Event()
_cleanup_thread: threading.Thread | None = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _startup_seconds
    sc = _app_config.session
    if isinstance(_session_store, MemorySessionStore) and sc.cleanup_interval > 0:
        _cleanup_event.clear()
        _cleanup_thread = threading.Thread(
            target=_session_store.cleanup_loop,
            args=(sc.cleanup_interval, _cleanup_event),
            daemon=True,
        )
        _cleanup_thread.start()
    _startup_seconds = round(time.time() - _START_TIME, 2)
    set_startup_seconds(_startup_seconds)
    yield
    if _cleanup_thread is not None:
        _cleanup_event.set()
        _cleanup_thread.join(timeout=5)


# ---- app factory ----

app = FastAPI(title="KF API", version=APP_VERSION, lifespan=_lifespan)


@app.middleware("http")
async def _charset_middleware(request: Request, call_next):
    response = await call_next(request)
    ct = response.headers.get("content-type", "")
    if "application/json" in ct and "charset" not in ct:
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(AuthMiddleware, config=_app_config.auth)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = get_request_id()
    _log.error(
        "unhandled exception",
        extra={
            "request_id": request_id,
            "path": str(request.url.path),
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal server error",
            "detail": "服务器内部错误，请稍后重试或联系管理员",
            "request_id": request_id,
        },
    )


# ---- config reload gate ----

@app.middleware("http")
async def _reload_gate(request: Request, call_next):
    if request.url.path == "/reload":
        return await call_next(request)
    cfg = get_app_config()
    if cfg.need_reload:
        return JSONResponse(
            status_code=503,
            content={"error": "service briefly unavailable — config reload in progress"},
            headers={"Retry-After": "1"},
        )
    return await call_next(request)


# ---- health / ready / status / reload / metrics (always available) ----


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time(), "startup_seconds": get_startup_seconds()}


@app.get("/ready")
async def ready():
    probes: dict[str, str] = {}
    try:
        from src.rag.qdrant import QdrantSearch

        qdrant = QdrantSearch()
        qdrant._client.get_collections()
        probes["qdrant"] = "ok"
    except Exception as e:
        probes["qdrant"] = f"error: {e}"
    try:
        import httpx2

        embed_provider = _app_config.embed_provider()
        base = embed_provider.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        resp = httpx2.get(f"{base}/health", timeout=5)
        probes["embedding"] = "ok" if resp.status_code == 200 else f"status {resp.status_code}"
    except Exception as e:
        probes["embedding"] = f"error: {e}"
    try:
        from src.db import get_db_pool  # noqa: F811

        db_cfg = _app_config.db
        if db_cfg and db_cfg.pools:
            pool_names = list(db_cfg.pools.keys())
            available = []
            for name in pool_names:
                try:
                    pool = get_db_pool(name)
                    pool.execute("SELECT 1")
                    available.append(name)
                except Exception as e:
                    available.append(f"{name}: {type(e).__name__}")
            probes["db_pools"] = ", ".join(available) if available else "no pools"
        else:
            probes["db_pools"] = "not configured"
    except Exception as e:
        probes["db_pools"] = f"error: {e}"
    cfg = get_app_config()
    return {
        "status": "ready",
        "probes": probes,
        "workflows": list(cfg.workflows.keys()),
        "llm_default": cfg.llm.default if cfg.llm else None,
        "embed_default": cfg.embed.default if cfg.embed else None,
    }


@app.post("/reload")
async def reload_config(sync: str = "local"):
    if sync not in ("local", "oss"):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid sync parameter", "detail": "sync must be 'local' or 'oss'"},
        )
    new_cfg = await asyncio.to_thread(reload_app_config, sync_oss=(sync == "oss"))
    _log.info("config reloaded", extra={"workflows": list(new_cfg.workflows.keys()), "sync": sync})
    return {"status": "ok", "workflows": list(new_cfg.workflows.keys()), "sync": sync}


@app.get("/status")
async def status():
    cfg = get_app_config()
    components: dict[str, dict] = {}
    components["qdrant"] = probe(probe_qdrant)
    try:
        llm_provider = cfg.llm_provider()
        components["llm"] = probe(lambda: probe_ollama(llm_provider))
    except Exception as e:
        components["llm"] = {"status": "error", "latency_ms": 0, "detail": str(e)}
    try:
        embed_provider = cfg.embed_provider()
        components["embedding"] = probe(lambda: probe_embed(embed_provider))
    except Exception as e:
        components["embedding"] = {"status": "error", "latency_ms": 0, "detail": str(e)}
    components["metrics_store"] = probe(
        lambda: _metrics_store.health_check().get("detail", "")
    )
    db_cfg = cfg.db
    if db_cfg and getattr(db_cfg, "pools", None):
        from src.db import get_db_pool  # noqa: F811

        def _probe_pools() -> str:
            results = []
            for name in db_cfg.pools:
                try:
                    get_db_pool(name).execute("SELECT 1")
                    results.append(f"{name}:ok")
                except Exception as e:
                    results.append(f"{name}:{type(e).__name__}")
            return ", ".join(results)

        components["db_pools"] = probe(_probe_pools)
    overall = "ok" if all(c["status"] == "ok" for c in components.values()) else "degraded"
    import platform as _platform

    process = {
        "version": APP_VERSION,
        "python": _platform.python_version(),
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "workflow_count": len(cfg.workflows),
        "workflows": list(cfg.workflows.keys()),
    }
    return {
        "status": overall,
        "timestamp": time.time(),
        "components": components,
        "process": process,
    }


@app.get("/metrics")
async def metrics():
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(generate_latest(), media_type="text/plain")


# ---- conditional route inclusion (KF_MODE) ----

_mode = os.environ.get("KF_MODE", "full")

if _mode in ("full", "chat"):
    app.include_router(chat_router)
    app.include_router(export_router)

if _mode in ("full", "admin"):
    app.include_router(admin_api_router)
    app.include_router(admin_base_router)
