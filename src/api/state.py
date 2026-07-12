"""Shared application state and utility functions for API route modules.

Module-level singletons are set by ``main.py`` during startup.
Route modules import the ``get_*()`` functions to access them lazily
(at request time, not at import time).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

APP_VERSION = "0.2.0"
_START_TIME = time.time()
_startup_seconds: float | None = None

# ---- singletons ----
_metrics_store = None
_session_store = None
_dag_engine = None
_registry = None


def set_startup_seconds(val: float):
    global _startup_seconds
    _startup_seconds = val


def get_startup_seconds() -> float | None:
    return _startup_seconds


def get_start_time() -> float:
    return _START_TIME


def set_metrics_store(store):
    global _metrics_store
    _metrics_store = store


def get_metrics_store():
    return _metrics_store


def set_session_store(store):
    global _session_store
    _session_store = store


def get_session_store():
    return _session_store


def set_dag_engine(engine):
    global _dag_engine
    _dag_engine = engine


def get_dag_engine():
    return _dag_engine


def set_registry(reg):
    global _registry
    _registry = reg


def get_registry():
    return _registry


# ---- utility functions ----

def make_qdrant():
    from src.config import get_app_config
    from src.rag.qdrant import QdrantSearch

    qc = get_app_config().qdrant
    return QdrantSearch(host=qc.host, port=qc.port)


def make_embed_client():
    from src.config import get_app_config
    from src.llm.client import LLMClient

    provider = get_app_config().embed_provider()
    return LLMClient(base_url=provider.base_url, api_key=provider.api_key)


def embed_model_name() -> str:
    from src.config import get_app_config

    return get_app_config().embed_provider().model


def build_response(session) -> dict:
    reply = ""
    if session.history:
        reply = session.history[-1].output
    return {
        "chat_id": session.chat_id,
        "turn_id": session.turn_id,
        "reply": reply,
    }


def sanitize_filename(name: str) -> str:
    keep = [c for c in name if c.isalnum() or c in ("-", "_")]
    return ("".join(keep) or "chat_history")[:80]


def probe(fn) -> dict:
    t0 = time.time()
    try:
        detail = fn()
        return {
            "status": "ok",
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "detail": detail or "",
        }
    except Exception as e:
        return {
            "status": "error",
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "detail": f"{type(e).__name__}: {e}",
        }


def probe_qdrant() -> str:
    qc = make_qdrant()
    cols = qc._client.get_collections()
    n = len(getattr(cols, "collections", []) or [])
    return f"{n} collections"


def probe_ollama(provider) -> str:
    import httpx2

    base = provider.base_url.rstrip("/")
    resp = httpx2.get(f"{base}/models", timeout=5)
    if resp.status_code >= 500:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return (
        f"provider={provider.type} model={provider.model} "
        f"host={_host_of(base)} (HTTP {resp.status_code})"
    )


def probe_embed(provider) -> str:
    import httpx2

    base = provider.base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    resp = httpx2.get(f"{base}/health", timeout=5)
    if resp.status_code >= 500:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return f"model={provider.model} host={_host_of(base)} (HTTP {resp.status_code})"


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc or url
    except Exception:
        return url
