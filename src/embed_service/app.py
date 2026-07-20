"""kf-embed FastAPI 应用 —— OpenAI 兼容 Embedding 服务。

暴露接口:
    POST /v1/embeddings   OpenAI 兼容向量化端点
    GET  /health          存活探针（进程可用即 200）
    GET  /ready           就绪探针（模型加载完成才 200）

环境变量:
    EMBED_MODEL    默认模型名（默认 nomic-ai/nomic-embed-text-v1.5）
    EMBED_WARMUP   是否在启动时预热加载模型（默认 "1" 开启）
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.embed_service.service import DEFAULT_MODEL, embed_texts, get_model, is_ready
import logging

logger = logging.getLogger(__name__)

# 进程导入时刻 + 模型就绪耗时（供 /ready 报告启动时间，避免外部轮询阻塞）
_PROCESS_START = time.time()
_startup_seconds: float | None = None

# 鉴权放行路径（探针无需 Key，供 K8s livenessProbe/readinessProbe 使用）
_AUTH_SKIP_PATHS = ("/health", "/ready")


def _default_model() -> str:
    """读取环境变量决定默认模型名。"""
    return os.environ.get("EMBED_MODEL") or DEFAULT_MODEL


def _api_key() -> str:
    """读取环境变量中的 API Key；为空则关闭鉴权（开发模式）。"""
    return os.environ.get("EMBED_API_KEY", "")


def _extract_key(request: Request) -> str:
    """从请求头提取客户端 Key，兼容 X-API-Key 与 Authorization: Bearer。"""
    provided = request.headers.get("X-API-Key", "")
    if not provided:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            provided = auth[7:]
    return provided


class EmbeddingRequest(BaseModel):
    """OpenAI 兼容的向量化请求体。"""

    input: str | list[str]
    model: str = ""


@asynccontextmanager
async def lifespan(_app: FastAPI):  # pragma: no cover - 依赖真实模型加载
    """应用生命周期：可选地在启动时预热模型，并记录就绪耗时。"""
    global _startup_seconds
    if os.environ.get("EMBED_WARMUP", "1") == "1":
        logger.info("Warmup starting...")
        t0 = time.time()
        get_model(_default_model())
        _startup_seconds = round(time.time() - _PROCESS_START, 2)
        t1 = time.time()
        logger.info("Warmup complete, took %.2fs (send_%.2fs)",
                    _startup_seconds, t1 - t0)
    else:
        logger.info("Warmup disabled (EMBED_WARMUP != 1)")
    yield


app = FastAPI(title="kf-embed", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def _auth(request: Request, call_next):
    """API Key 鉴权中间件。

    - EMBED_API_KEY 未设置 → 放行所有请求（开发模式）
    - /health、/ready 探针始终放行
    - 其余请求校验 X-API-Key 或 Authorization: Bearer <key>
    """
    key = _api_key()
    if key and request.url.path not in _AUTH_SKIP_PATHS:
        if _extract_key(request) != key:
            return JSONResponse(
                status_code=401,
                content={"error": "invalid or missing API key"},
            )
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    """存活探针：进程运行即返回 ok。"""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    """就绪探针：模型未加载完成时返回 503；就绪时附带启动耗时。"""
    if not is_ready():
        raise HTTPException(status_code=503, detail="model not loaded")
    return {"status": "ready", "startup_seconds": _startup_seconds}


@app.post("/v1/embeddings")
def embeddings(req: EmbeddingRequest) -> dict:
    """OpenAI 兼容向量化端点。

    请求: {"model": "nomic-embed-text", "input": "text" | ["t1", "t2"]}
    响应: {"object": "list", "data": [{"embedding": [...], "index": 0}], ...}
    """
    inputs = [req.input] if isinstance(req.input, str) else list(req.input)
    if not inputs or any(not isinstance(t, str) for t in inputs):
        raise HTTPException(
            status_code=400,
            detail="input must be a non-empty string or list of strings",
        )

    model_name = req.model or _default_model()
    vectors = embed_texts(inputs, model_name)

    data = [
        {"object": "embedding", "index": i, "embedding": vec}
        for i, vec in enumerate(vectors)
    ]
    # 粗略 token 估算（按空白切分），仅用于 usage 字段展示
    total_tokens = sum(len(t.split()) for t in inputs)
    return {
        "object": "list",
        "data": data,
        "model": model_name,
        "usage": {"prompt_tokens": total_tokens, "total_tokens": total_tokens},
    }
