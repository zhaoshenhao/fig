import asyncio
import json as _json
import queue
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api.auth import AuthMiddleware
from src.config import load_app_config
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
from src.ingestion.builder import build_directory, build_document
from src.llm.client import LLMClient
from src.logger import get_logger, init_logging
from src.logger.middleware import RequestIDMiddleware, get_request_id
from src.metrics import MetricsStore
from src.metrics.prometheus import MetricsMiddleware, generate_latest
from src.rag.qdrant import QdrantSearch
from src.session import MemorySessionStore, SessionData, SessionStore

_log = get_logger(__name__)


class RunRequest(BaseModel):
    query: str = Field(..., min_length=1, description="用户输入文本")
    chat_id: str | None = Field(None, description="会话 ID，续接多轮对话")
    long_mem_data: str | None = Field(None, description="长期记忆，client 管理")


class WorkflowInfo(BaseModel):
    name: str
    description: str = ""


class WorkflowList(BaseModel):
    workflows: list[WorkflowInfo]


_app_config = load_app_config()
init_logging(_app_config.logging.level, app_name="fastapi")
_metrics_store = MetricsStore()
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
_dag_engine = DAGEngine(
    tools=_registry, app_config=_app_config, metrics_store=_metrics_store,
)

if _app_config.db:
    from src.db import create_pool
    for name, pool_cfg in _app_config.db.pools.items():
        create_pool(name, pool_cfg)

_session_store: SessionStore = MemorySessionStore(
    max_age=getattr(_app_config.session, "max_age", 3600),
    max_sessions=getattr(_app_config.session, "memory_max_sessions", 2000),
)

_cleanup_event = threading.Event()
_cleanup_thread: threading.Thread | None = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    sc = _app_config.session
    if isinstance(_session_store, MemorySessionStore) and sc.cleanup_interval > 0:
        _cleanup_event.clear()
        _cleanup_thread = threading.Thread(
            target=_session_store.cleanup_loop,
            args=(sc.cleanup_interval, _cleanup_event),
            daemon=True,
        )
        _cleanup_thread.start()
    yield
    if _cleanup_thread is not None:
        _cleanup_event.set()
        _cleanup_thread.join(timeout=5)


app = FastAPI(
    title="KF API",
    version="0.1.0",
    lifespan=_lifespan,
)

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
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "detail": type(exc).__name__},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}


@app.get("/ready")
async def ready():
    probes: dict[str, str] = {}

    try:
        qdrant = QdrantSearch()
        qdrant._client.get_collections()
        probes["qdrant"] = "ok"
    except Exception as e:
        probes["qdrant"] = f"error: {e}"

    try:
        from src.config import get_app_config
        embed_provider = get_app_config().embed_provider()
        ollama_base = embed_provider.base_url.rstrip("/v1")
        import httpx2
        resp = httpx2.get(f"{ollama_base}/api/tags", timeout=5)
        if resp.status_code == 200:
            probes["ollama"] = "ok"
        else:
            probes["ollama"] = f"status {resp.status_code}"
    except Exception as e:
        probes["ollama"] = f"error: {e}"

    try:
        from src.config import get_app_config
        from src.db import get_db_pool
        db_cfg = get_app_config().db
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

    return {
        "status": "ready",
        "probes": probes,
        "workflows": list(_app_config.workflows.keys()),
        "llm_default": _app_config.llm.default if _app_config.llm else None,
        "embed_default": _app_config.embed.default if _app_config.embed else None,
    }


@app.get("/metrics")
async def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(generate_latest(), media_type="text/plain")


@app.get("/workflows", response_model=WorkflowList)
async def list_workflows():
    return WorkflowList(workflows=[
        WorkflowInfo(name=name, description=wf.get("description", ""))
        for name, wf in _app_config.workflows.items()
    ])


@app.get("/workflows/{name}")
async def get_workflow(name: str):
    wf = _app_config.workflows.get(name)
    if not wf:
        raise HTTPException(status_code=404, detail=f"workflow '{name}' not found")
    return {
        "name": name,
        "description": wf.get("description", ""),
        "collections": wf.get("collections", ["default"]),
        "return_mode": wf.get("return_mode", "full"),
        "nodes": [
            {
                "name": n["name"],
                "next_type": n.get("next_type", "one"),
                "next": n.get("next", ""),
                "metrics": n.get("metrics", False),
                "parallel": n.get("parallel", False),
            }
            for n in wf.get("nodes", [])
        ],
    }


@app.post("/workflows/{name}/run")
async def run_workflow(
    name: str, req: RunRequest, stream: bool = Query(False),
):
    wf = _app_config.workflows.get(name)
    if not wf:
        raise HTTPException(status_code=404, detail=f"workflow '{name}' not found")

    _log.info(
        "run workflow",
        extra={
            "request_id": get_request_id(),
            "workflow": name,
            "chat_id": req.chat_id or "",
            "stream": stream,
        },
    )

    session: SessionData | None = None
    if req.chat_id:
        session = _session_store.get(req.chat_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"session '{req.chat_id}' not found or expired",
            )
        if session.get("_workflow") != name:
            raise HTTPException(
                status_code=400,
                detail=f"session belongs to workflow '{session.get('_workflow')}', "
                f"cannot run with '{name}'",
            )

    if session is None:
        session = _session_store.create(name, wf.get("return_mode", "full"))

    if req.long_mem_data and req.long_mem_data.strip():
        session.long_mem_data = req.long_mem_data

    if not stream:
        await asyncio.to_thread(
            _dag_engine.run, name, {"query": req.query}, session
        )
        session.nodes.clear()
        _session_store.save(session)
        return _build_response(session)

    return StreamingResponse(
        _stream_workflow_events(name, req, session, wf),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


async def _stream_workflow_events(
    workflow_name: str, req: RunRequest, session: SessionData, wf: dict,
):
    event_queue: queue.Queue[str | None] = queue.Queue()

    def _on_token(token: str):
        event_queue.put(token)

    session.stream_callback = _on_token

    finish_evt: dict[str, object] = {}

    def _run_blocking():
        try:
            _dag_engine.run(workflow_name, {"query": req.query}, session)
        except Exception as exc:
            finish_evt["error"] = str(exc)
        finally:
            event_queue.put(None)

    t = threading.Thread(target=_run_blocking, daemon=True)
    t.start()

    sent_node_start = False
    while True:
        token = await asyncio.to_thread(event_queue.get)
        if token is None:
            if sent_node_start:
                yield "event: node_end\n\n"
            break
        if not sent_node_start:
            yield "data: {}\n\n".format(
                _json.dumps(
                    {"event": "status", "node": "start", "workflow": workflow_name},
                    ensure_ascii=False,
                )
            )
            yield "event: node_start\n\n"
            sent_node_start = True
        yield "data: {}\n\n".format(
            _json.dumps({"event": "token", "data": token}, ensure_ascii=False)
        )

    session.nodes.clear()
    _session_store.save(session)

    if finish_evt.get("error"):
        yield "data: {}\n\n".format(
            _json.dumps(
                {"event": "error", "data": str(finish_evt["error"])},
                ensure_ascii=False,
            )
        )
        return

    reply = _build_response(session)
    yield "data: {}\n\n".format(
        _json.dumps(
            {"event": "done", **reply},
            ensure_ascii=False,
        )
    )


@app.delete("/sessions/{chat_id}")
async def delete_session(chat_id: str):
    deleted = _session_store.delete(chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"session '{chat_id}' not found")
    return JSONResponse(status_code=204, content=None)


def _build_response(session: SessionData) -> dict:
    reply = ""
    if session.history:
        reply = session.history[-1].output
    return {
        "chat_id": session.chat_id,
        "turn_id": session.turn_id,
        "reply": reply,
    }


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form(default="default"),
    chunk_size: int = Form(default=800),
    chunk_overlap: int = Form(default=64),
):
    staging = Path("data/staging")
    staging.mkdir(parents=True, exist_ok=True)

    filepath = staging / (file.filename or "untitled")
    content = await file.read()
    filepath.write_bytes(content)

    def _build():
        qdrant = _make_qdrant()
        embed_client = _make_embed_client()
        embed_model = _embed_model_name()
        return build_document(
            filepath, collection, qdrant, embed_client, embed_model,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        )

    count = await asyncio.to_thread(_build)
    return {
        "status": "ok",
        "file": file.filename,
        "collection": collection,
        "chunks": count,
    }


@app.post("/documents/scan")
async def scan_directory(
    directory: str = Form(default="data/documents"),
    collection: str = Form(default="default"),
    chunk_size: int = Form(default=800),
    chunk_overlap: int = Form(default=64),
):
    target = Path(directory)
    if not target.is_dir():
        raise HTTPException(
            status_code=400, detail=f"directory '{directory}' not found"
        )

    def _build():
        qdrant = _make_qdrant()
        embed_client = _make_embed_client()
        embed_model = _embed_model_name()
        return build_directory(
            target, collection, qdrant, embed_client, embed_model,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        )

    count = await asyncio.to_thread(_build)
    return {
        "status": "ok",
        "directory": str(target),
        "collection": collection,
        "chunks": count,
    }


class DeletePointsRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, description="要删除的点 ID 列表")


@app.get("/collections")
async def list_collections():
    qdrant = _make_qdrant()
    names = qdrant.list_collections()
    return {"collections": names}


@app.get("/collections/{name}")
async def get_collection(name: str):
    qdrant = _make_qdrant()
    try:
        info = qdrant.collection_info(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return info


@app.delete("/collections/{name}")
async def delete_collection(name: str):
    qdrant = _make_qdrant()
    try:
        qdrant.delete_collection(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deleted", "collection": name}


@app.delete("/collections/{name}/points")
async def delete_collection_points(name: str, req: DeletePointsRequest):
    qdrant = _make_qdrant()
    try:
        result = qdrant.delete_points(name, req.ids)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.get("/collections/{name}/browse")
async def browse_collection(
    name: str,
    limit: int = 20,
    offset: int = 0,
):
    qdrant = _make_qdrant()
    results, next_offset = qdrant.scroll(name, limit=limit, offset=offset)
    return {
        "collection": name,
        "points": results,
        "next_offset": next_offset,
    }


@app.get("/collections/{name}/count")
async def count_collection(name: str):
    qdrant = _make_qdrant()
    try:
        n = qdrant.count(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"collection": name, "count": n}


# ---- 指标查询端点 ----


@app.get("/sessions")
async def list_sessions(limit: int = 50, offset: int = 0):
    return {"sessions": _metrics_store.query_sessions(limit=limit, offset=offset)}


@app.get("/sessions/{chat_id}")
async def get_session_turns(chat_id: str, limit: int = 50, offset: int = 0):
    turns = _metrics_store.query_session_turns(chat_id, limit=limit, offset=offset)
    if not turns:
        raise HTTPException(status_code=404, detail="session not found")
    return {"chat_id": chat_id, "turns": turns}


@app.get("/sessions/{chat_id}/turns/{turn_id}")
async def get_turn_nodes(chat_id: str, turn_id: int):
    turns = _metrics_store.query_session_turns(chat_id)
    run = next((t for t in turns if t.get("turn_id") == turn_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="turn not found")
    run_id = run["run_id"]
    nodes = _metrics_store.query_turn_nodes(run_id)
    return {"chat_id": chat_id, "turn_id": turn_id, "run": run, "nodes": nodes}


@app.get("/sessions/{chat_id}/turns/{turn_id}/nodes/{node_name}")
async def get_node_tools(chat_id: str, turn_id: int, node_name: str):
    turns = _metrics_store.query_session_turns(chat_id)
    run = next((t for t in turns if t.get("turn_id") == turn_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="turn not found")
    nodes = _metrics_store.query_turn_nodes(run["run_id"])
    node = next((n for n in nodes if n.get("node_name") == node_name), None)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    tools = _metrics_store.query_node_tools(node["node_log_id"])
    return {
        "chat_id": chat_id, "turn_id": turn_id,
        "node_name": node_name, "node": node, "tools": tools,
    }


_UI_DIR = Path(__file__).resolve().parent.parent / "gui" / "ui" / "dist"
if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")


def _make_qdrant() -> QdrantSearch:
    import os
    return QdrantSearch(
        host=os.environ.get("QDRANT_HOST", "localhost"),
        port=int(os.environ.get("QDRANT_PORT", "6334")),
    )


def _make_embed_client() -> LLMClient:
    from src.config import get_app_config
    provider = get_app_config().embed_provider()
    return LLMClient(base_url=provider.base_url, api_key=provider.api_key)


def _embed_model_name() -> str:
    from src.config import get_app_config
    return get_app_config().embed_provider().model
