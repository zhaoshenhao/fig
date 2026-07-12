"""Admin API routes – internal dashboard, metrics, and management."""

from __future__ import annotations

import asyncio
import json as _json

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.state import (
    embed_model_name,
    get_metrics_store,
    make_embed_client,
    make_qdrant,
)
from src.logger import get_logger

_log = get_logger(__name__)

admin_api_router = APIRouter(prefix="/api/v1")
admin_base_router = APIRouter()


# ---- Models ----


class DeletePointsRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, description="要删除的点 ID 列表")


# ---- Sessions (admin search) ----
#    registered on admin_api_router (prefix=/api/v1)


@admin_api_router.get("/sessions")
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    time_from: str | None = None,
    time_to: str | None = None,
    workflow: str | None = None,
    node: str | None = None,
    tool: str | None = None,
    input_text: str | None = None,
    output_text: str | None = None,
    duration_min: float | None = None,
    duration_max: float | None = None,
    feedback: str | None = None,
    title: str | None = None,
    sort_by: str = "last_at",
    sort_dir: str = "desc",
):
    metrics_store = get_metrics_store()
    rows, total = metrics_store.search_sessions(
        time_from=time_from,
        time_to=time_to,
        workflow=workflow,
        node=node,
        tool=tool,
        input_text=input_text,
        output_text=output_text,
        duration_min=duration_min,
        duration_max=duration_max,
        feedback=feedback,
        title=title,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    return {"sessions": rows, "total": total}


@admin_api_router.get("/sessions/{chat_id}")
async def get_session_turns(chat_id: str, limit: int = 50, offset: int = 0):
    metrics_store = get_metrics_store()
    turns = metrics_store.query_session_turns(chat_id, limit=limit, offset=offset)
    if not turns:
        raise HTTPException(status_code=404, detail="session not found")
    return {"chat_id": chat_id, "turns": turns}


@admin_api_router.get("/sessions/{chat_id}/turns/{turn_id}/feedback")
async def get_feedback_admin(chat_id: str, turn_id: int):
    rows = await asyncio.to_thread(
        get_metrics_store().query_feedback, chat_id, turn_id
    )
    return {"chat_id": chat_id, "turn_id": turn_id, "feedback": rows}


# ---- Metrics ----
#    registered on admin_base_router (no prefix)


@admin_base_router.get("/metrics/summary")
async def metrics_summary(time_from: str | None = None, time_to: str | None = None):
    return get_metrics_store().aggregate_summary(time_from=time_from, time_to=time_to)


@admin_base_router.get("/metrics/timeseries")
async def metrics_timeseries(
    workflow: str = Query(..., min_length=1),
    time_from: str | None = None,
    time_to: str | None = None,
):
    return get_metrics_store().timeseries(workflow, time_from=time_from, time_to=time_to)


@admin_base_router.post("/metrics/retention")
async def metrics_retention(
    days: int = Query(..., ge=1, description="保留天数，删除更早的记录"),
):
    import datetime as _dt

    cutoff = (_dt.datetime.now(_dt.UTC) - _dt.timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    deleted = await asyncio.to_thread(
        get_metrics_store().delete_older_than, cutoff
    )
    return {"status": "ok", "cutoff": cutoff, "deleted_runs": deleted}


@admin_base_router.get("/metrics/feedback")
async def metrics_feedback(
    rating: str | None = None,
    workflow: str | None = None,
    limit: int = 200,
):
    rows = await asyncio.to_thread(
        get_metrics_store().list_feedback, rating, workflow, limit
    )
    return {"feedback": rows, "count": len(rows)}


@admin_base_router.get("/metrics/rag")
async def rag_summary(
    workflow: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
):
    return get_metrics_store().rag_summary(
        workflow=workflow, time_from=time_from, time_to=time_to
    )


@admin_base_router.get("/export/training.jsonl")
async def export_training(
    workflow: str | None = None,
    status: str = "ok",
    limit: int = 1000,
    only_feedback: str | None = None,
):
    metrics_store = get_metrics_store()
    samples = metrics_store.export_training(
        workflow=workflow, status=status, limit=limit, only_feedback=only_feedback
    )
    lines = "\n".join(_json.dumps(s, ensure_ascii=False) for s in samples)
    return Response(
        content=(lines + ("\n" if lines else "")).encode("utf-8"),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="training.jsonl"'},
    )


# ---- Collections ----
#    registered on admin_base_router (no prefix)


@admin_base_router.get("/collections")
async def list_collections():
    return {"collections": make_qdrant().list_collections()}


@admin_base_router.get("/collections/{name}")
async def get_collection(name: str):
    try:
        return make_qdrant().collection_info(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@admin_base_router.delete("/collections/{name}")
async def delete_collection(name: str):
    try:
        make_qdrant().delete_collection(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deleted", "collection": name}


@admin_base_router.delete("/collections/{name}/points")
async def delete_collection_points(name: str, req: DeletePointsRequest):
    try:
        return make_qdrant().delete_points(name, req.ids)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_base_router.get("/collections/{name}/browse")
async def browse_collection(name: str, limit: int = 20, offset: int = 0):
    results, next_offset = make_qdrant().scroll(name, limit=limit, offset=offset)
    return {"collection": name, "points": results, "next_offset": next_offset}


@admin_base_router.get("/collections/{name}/search")
async def search_collection(name: str, q: str = Query(..., min_length=1), limit: int = 10):
    try:
        embed_client = make_embed_client()
        vectors = await asyncio.to_thread(embed_client.embed, embed_model_name(), q)
        vector = vectors[0] if vectors else []
        if not vector:
            raise ValueError("embedding 返回空向量")
        results = await asyncio.to_thread(
            make_qdrant().search, name, vector, q, limit,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"检索失败: {e}")
    points = [
        {
            "id": r.get("id"),
            "score": r.get("score"),
            "text": (r.get("payload") or {}).get("text", ""),
            "source": (r.get("payload") or {}).get("source", ""),
        }
        for r in results
    ]
    return {"collection": name, "query": q, "points": points}


@admin_base_router.get("/collections/{name}/count")
async def count_collection(name: str):
    try:
        n = make_qdrant().count(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"collection": name, "count": n}


# ---- Documents ----
#    registered on admin_base_router (no prefix)


@admin_base_router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form(default="default"),
    chunk_size: int = Form(default=800),
    chunk_overlap: int = Form(default=64),
    rebuild: bool = Form(default=False),
):
    from pathlib import Path

    staging = Path("data/staging")
    staging.mkdir(parents=True, exist_ok=True)

    filepath = staging / (file.filename or "untitled")
    content = await file.read()
    filepath.write_bytes(content)

    def _build():
        from src.ingestion.builder import build_document

        qdrant = make_qdrant()
        if rebuild:
            try:
                qdrant.delete_collection(collection)
            except Exception as e:
                _log.info(
                    "rebuild: drop collection skipped",
                    extra={"collection": collection, "error": str(e)},
                )
        ec = make_embed_client()
        em = embed_model_name()
        return build_document(
            filepath, collection, qdrant, ec, em,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        )

    count = await asyncio.to_thread(_build)
    return {
        "status": "ok",
        "file": file.filename,
        "collection": collection,
        "chunks": count,
        "rebuilt": rebuild,
    }


@admin_base_router.post("/documents/scan")
async def scan_directory(
    directory: str = Form(default="data/documents"),
    collection: str = Form(default="default"),
    chunk_size: int = Form(default=800),
    chunk_overlap: int = Form(default=64),
    rebuild: bool = Form(default=False),
):
    from pathlib import Path

    target = Path(directory)
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"directory '{directory}' not found")

    def _build():
        from src.ingestion.builder import build_directory

        qdrant = make_qdrant()
        if rebuild:
            try:
                qdrant.delete_collection(collection)
            except Exception as e:
                _log.info(
                    "rebuild: drop collection skipped",
                    extra={"collection": collection, "error": str(e)},
                )
        ec = make_embed_client()
        em = embed_model_name()
        return build_directory(
            target, collection, qdrant, ec, em,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        )

    count = await asyncio.to_thread(_build)
    return {
        "status": "ok",
        "directory": str(target),
        "collection": collection,
        "chunks": count,
        "rebuilt": rebuild,
    }
