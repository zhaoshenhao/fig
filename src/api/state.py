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
    import httpx2
    import re

    qc = make_qdrant()
    cols = qc._client.get_collections()
    n = len(getattr(cols, "collections", []) or [])
    detail = f"{n} collections"
    try:
        info = qc._client.info()
        detail += f", version={info.version}"
    except Exception:
        pass
    try:
        host = qc.host
        rest_port = qc.port - 1
        resp = httpx2.get(f"http://{host}:{rest_port}/metrics", timeout=5)
        if resp.status_code == 200:
            m = re.search(r"memory_resident_bytes\s+(\d+)", resp.text)
            if m:
                mem = int(m.group(1))
                detail += f", mem={round(mem/(1024*1024),1)}MB"
    except Exception:
        pass
    return detail


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
    detail = f"model={provider.model} host={_host_of(base)} (HTTP {resp.status_code})"
    mem = resp.json().get("memory_mb", 0) if resp.status_code == 200 else 0
    if mem:
        detail += f" [{mem}MB]"
    try:
        ready = httpx2.get(f"{base}/ready", timeout=5)
        if ready.status_code == 200:
            mi = ready.json().get("model", {})
            if mi:
                detail += f" [{mi.get('model_file','')} dim={mi.get('dim','')} size={mi.get('size_in_GB','')}GB]"
    except Exception:
        pass
    try:
        import fastembed
        detail += f" fastembed={fastembed.__version__}"
    except Exception:
        pass
    return detail


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc or url
    except Exception:
        return url
