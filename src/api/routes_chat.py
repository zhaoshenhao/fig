"""Chat API routes – user-facing workflow execution and session management."""

from __future__ import annotations

import asyncio
import json as _json
import queue
import threading
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from src.api.state import (
    build_response,
    get_dag_engine,
    get_metrics_store,
    get_session_store,
    sanitize_filename,
)
from src.config import get_app_config
from src.logger import get_logger
from src.logger.middleware import get_request_id

_log = get_logger(__name__)

chat_router = APIRouter(prefix="/api/v1")
export_router = APIRouter(prefix="/export")


# ---- Models ----


class RunRequest(BaseModel):
    query: str = Field(..., min_length=1, description="用户输入文本")
    chat_id: str | None = Field(None, description="会话 ID，续接多轮对话")
    long_mem_data: str | None = Field(None, description="长期记忆，client 管理")


class FeedbackRequest(BaseModel):
    rating: str = Field(..., description="up | down")
    comment: str | None = Field(None, description="可选评论")
    correction: str | None = Field(None, description="可选纠错答案")


class RegenerateRequest(BaseModel):
    chat_id: str = Field(..., description="要重新生成的会话 ID")


class SessionMetaRequest(BaseModel):
    title: str | None = Field(None, description="会话标题")
    tags: list[str] | None = Field(None, description="标签列表")


class ChatMessage(BaseModel):
    role: str = ""
    content: str = ""
    ts: str | None = None
    feedback: str | None = None
    comment: str | None = None
    correction: str | None = None


class ChatExportRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    filename: str = "chat_history"


# ---- Streaming helper ----


async def _stream_workflow_events(workflow_name, req, session, wf):
    event_queue: queue.Queue[str | None] = queue.Queue()
    engine = get_dag_engine()
    session_store = get_session_store()

    def _on_token(token):
        event_queue.put(token)

    session.stream_callback = _on_token
    finish_evt: dict[str, object] = {}

    def _run_blocking():
        try:
            engine.run(workflow_name, {"query": req.query}, session)
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
    session_store.save(session)

    if finish_evt.get("error"):
        yield "data: {}\n\n".format(
            _json.dumps(
                {"event": "error", "data": str(finish_evt["error"])},
                ensure_ascii=False,
            )
        )
        return

    reply = build_response(session)
    yield "data: {}\n\n".format(
        _json.dumps({"event": "done", **reply}, ensure_ascii=False)
    )


# ---- Workflows ----
#    registered on chat_router (prefix=/api/v1)


@chat_router.get("/workflows")
async def list_workflows():
    cfg = get_app_config()
    return {
        "workflows": [
            {"name": name, "description": wf.get("description", "")}
            for name, wf in cfg.workflows.items()
        ]
    }


@chat_router.get("/workflows/{name}")
async def get_workflow(name: str):
    cfg = get_app_config()
    wf = cfg.workflows.get(name)
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
                "tool": cfg.nodes.get(f"{name}:{n['name']}", {}).get("tool", ""),
                "next_type": n.get("next_type", "one"),
                "next": n.get("next", ""),
                "metrics": n.get("metrics", False),
                "parallel": n.get("parallel", False),
                "config": cfg.nodes.get(f"{name}:{n['name']}", {}),
            }
            for n in wf.get("nodes", [])
        ],
    }


@chat_router.get("/workflows/{name}/yaml")
async def get_workflow_yaml(name: str):
    cfg = get_app_config()
    wf = cfg.workflows.get(name)
    if not wf:
        raise HTTPException(status_code=404, detail=f"workflow '{name}' not found")
    content = wf.get("_raw_yaml", "")
    return {"name": name, "content": content}


@chat_router.post("/workflows/{name}/run")
async def run_workflow(name: str, req: RunRequest, stream: bool = Query(False)):
    session_store = get_session_store()
    engine = get_dag_engine()
    cfg = get_app_config()
    wf = cfg.workflows.get(name)
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

    session = None
    if req.chat_id:
        session = session_store.get(req.chat_id)
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
        session = session_store.create(name, wf.get("return_mode", "full"))

    if req.long_mem_data and req.long_mem_data.strip():
        session.long_mem_data = req.long_mem_data

    if not stream:
        await asyncio.to_thread(engine.run, name, {"query": req.query}, session)
        session.nodes.clear()
        session_store.save(session)
        return build_response(session)

    return StreamingResponse(
        _stream_workflow_events(name, req, session, wf),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@chat_router.post("/workflows/{name}/regenerate")
async def regenerate(name: str, req: RegenerateRequest, stream: bool = Query(False)):
    session_store = get_session_store()
    engine = get_dag_engine()
    cfg = get_app_config()
    wf = cfg.workflows.get(name)
    if not wf:
        raise HTTPException(status_code=404, detail=f"workflow '{name}' not found")

    session = session_store.get(req.chat_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail=f"session '{req.chat_id}' not found or expired"
        )
    if session.get("_workflow") != name:
        raise HTTPException(
            status_code=400,
            detail=f"session belongs to workflow '{session.get('_workflow')}'",
        )
    if not session.history:
        raise HTTPException(status_code=400, detail="no previous turn to regenerate")

    last_query = session.history[-1].input
    if not last_query:
        raise HTTPException(status_code=400, detail="last turn has empty query")

    run_req = RunRequest(query=last_query, chat_id=req.chat_id)
    if not stream:
        await asyncio.to_thread(engine.run, name, {"query": last_query}, session)
        session.nodes.clear()
        session_store.save(session)
        return build_response(session)

    return StreamingResponse(
        _stream_workflow_events(name, run_req, session, wf),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ---- Sessions ----
#    registered on chat_router (prefix=/api/v1)


@chat_router.delete("/sessions/{chat_id}")
async def delete_session(chat_id: str):
    deleted = get_session_store().delete(chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"session '{chat_id}' not found")
    return JSONResponse(status_code=204, content=None)


@chat_router.get("/sessions/{chat_id}/meta")
async def get_session_meta(chat_id: str):
    session_store = get_session_store()
    metrics_store = get_metrics_store()
    session = session_store.get(chat_id)
    if session is not None:
        meta = metrics_store.get_session_meta(chat_id)
        return {
            "chat_id": chat_id,
            "title": getattr(session, "title", "") or meta.get("title", ""),
            "tags": getattr(session, "tags", []) or meta.get("tags", []),
            "workflow": session.get("_workflow"),
            "turn_id": session.turn_id,
        }
    meta = metrics_store.get_session_meta(chat_id)
    return {
        "chat_id": chat_id,
        "title": meta.get("title", ""),
        "tags": meta.get("tags", []),
        "workflow": None,
        "turn_id": None,
    }


@chat_router.patch("/sessions/{chat_id}/meta")
async def update_session_meta(chat_id: str, req: SessionMetaRequest):
    session_store = get_session_store()
    metrics_store = get_metrics_store()
    session = session_store.get(chat_id)
    if session is not None:
        if req.title is not None:
            session.title = req.title
        if req.tags is not None:
            session.tags = req.tags
        session_store.save(session)
    await asyncio.to_thread(
        metrics_store.upsert_session_meta, chat_id, req.title, req.tags
    )
    saved = metrics_store.get_session_meta(chat_id)
    return {
        "chat_id": chat_id,
        "title": saved.get("title", ""),
        "tags": saved.get("tags", []),
    }


@chat_router.get("/sessions/{chat_id}/turns/{turn_id}")
async def get_turn_nodes(chat_id: str, turn_id: int):
    metrics_store = get_metrics_store()
    turns = metrics_store.query_session_turns(chat_id)
    run = next((t for t in turns if t.get("turn_id") == turn_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="turn not found")
    run_id = run["run_id"]
    nodes = metrics_store.query_turn_nodes(run_id)
    feedback = metrics_store.query_feedback(chat_id, turn_id)
    rag = metrics_store.query_rag_for_turn(run_id)
    return {
        "chat_id": chat_id,
        "turn_id": turn_id,
        "run": run,
        "nodes": nodes,
        "feedback": feedback,
        "rag": rag,
    }


@chat_router.get("/sessions/{chat_id}/turns/{turn_id}/nodes/{node_name}")
async def get_node_tools(chat_id: str, turn_id: int, node_name: str):
    metrics_store = get_metrics_store()
    turns = metrics_store.query_session_turns(chat_id)
    run = next((t for t in turns if t.get("turn_id") == turn_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="turn not found")
    nodes = metrics_store.query_turn_nodes(run["run_id"])
    node = next((n for n in nodes if n.get("node_name") == node_name), None)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    tools = metrics_store.query_node_tools(node["node_log_id"])
    return {
        "chat_id": chat_id,
        "turn_id": turn_id,
        "node_name": node_name,
        "node": node,
        "tools": tools,
    }


@chat_router.get("/sessions/filters")
async def session_filters():
    return get_metrics_store().search_facets()


# ---- Feedback ----
#    registered on chat_router (prefix=/api/v1)


@chat_router.post("/sessions/{chat_id}/turns/{turn_id}/feedback")
async def submit_feedback(chat_id: str, turn_id: int, req: FeedbackRequest):
    if req.rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="rating must be 'up' or 'down'")
    metrics_store = get_metrics_store()
    fid = await asyncio.to_thread(
        metrics_store.insert_feedback,
        chat_id, turn_id, req.rating, req.comment, req.correction,
    )
    return {
        "status": "ok",
        "feedback_id": fid,
        "chat_id": chat_id,
        "turn_id": turn_id,
        "rating": req.rating,
    }


@chat_router.get("/sessions/{chat_id}/turns/{turn_id}/feedback")
async def get_feedback(chat_id: str, turn_id: int):
    rows = await asyncio.to_thread(
        get_metrics_store().query_feedback, chat_id, turn_id
    )
    return {"chat_id": chat_id, "turn_id": turn_id, "feedback": rows}


# ---- Utility ----
#    registered on chat_router (prefix=/api/v1)


@chat_router.get("/usage")
async def usage(time_from: str | None = None, time_to: str | None = None):
    metrics_store = get_metrics_store()
    summ = await asyncio.to_thread(
        metrics_store.aggregate_summary, time_from, time_to
    )
    ov = summ["overview"]
    return {
        "total_runs": ov["total_runs"],
        "total_sessions": ov["total_sessions"],
        "prompt_tokens": ov["prompt_tokens"],
        "completion_tokens": ov["completion_tokens"],
        "total_tokens": ov["prompt_tokens"] + ov["completion_tokens"],
        "error_rate": ov["error_rate"],
        "time_from": time_from,
        "time_to": time_to,
    }


@chat_router.get("/health")
async def health_v1():
    return {"status": "ok", "timestamp": time.time()}


# ---- Export ----
#    registered on export_router (prefix=/export)


@export_router.post("/chat.xlsx")
async def export_chat_xlsx(req: ChatExportRequest):
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "chat"
    ws.append(["role", "content", "timestamp", "feedback", "comment", "correction"])
    for m in req.messages:
        ws.append([
            m.role, m.content, m.ts or "",
            m.feedback or "", m.comment or "", m.correction or "",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    fname = sanitize_filename(req.filename)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'},
    )


@export_router.post("/chat.csv")
async def export_chat_csv(req: ChatExportRequest):
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["role", "content", "timestamp", "feedback", "comment", "correction"])
    for m in req.messages:
        writer.writerow([
            m.role, m.content, m.ts or "",
            m.feedback or "", m.comment or "", m.correction or "",
        ])
    fname = sanitize_filename(req.filename)
    data = ("\ufeff" + buf.getvalue()).encode("utf-8")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'},
    )
