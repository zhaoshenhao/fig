"""Embedding 模型加载与推理封装。

设计要点:
    - 懒加载单例：进程内只加载一次模型，多个请求共享同一实例。
    - 线程安全：uvicorn 多线程/多请求并发时用锁保护首次加载。
    - 别名映射：将 Ollama 风格模型名（nomic-embed-text）映射到
      FastEmbed 的 HuggingFace 仓库名（nomic-ai/nomic-embed-text-v1.5）。
    - fastembed 延迟导入：仅在真正加载模型时导入，便于在无该依赖的
      环境（如单元测试）中 mock。
"""

from __future__ import annotations

import os
import threading

# 默认模型（FastEmbed 仓库名）
DEFAULT_MODEL = "nomic-ai/nomic-embed-text-v1.5"

# Ollama / OpenAI 风格别名 -> FastEmbed 仓库名
MODEL_ALIASES = {
    "nomic-embed-text": "nomic-ai/nomic-embed-text-v1.5",
    "nomic-embed-text-v1.5": "nomic-ai/nomic-embed-text-v1.5",
    "": DEFAULT_MODEL,
}

_model = None  # 已加载的模型实例
_model_name = None  # 当前已加载模型的规范名
_lock = threading.Lock()  # 首次加载互斥锁


def resolve_model_name(name: str) -> str:
    """将请求中的模型名解析为 FastEmbed 规范仓库名。

    Args:
        name: 客户端请求的模型名（可能是别名或空字符串）

    Returns:
        FastEmbed 可识别的模型仓库名
    """
    return MODEL_ALIASES.get(name, name)


def _load_model(name: str):  # pragma: no cover - 需 fastembed 及模型下载
    """加载 FastEmbed 模型（延迟导入 fastembed）。"""
    from fastembed import TextEmbedding

    cache_dir = os.environ.get("EMBED_CACHE_DIR", os.path.join(os.getcwd(), "model"))
    return TextEmbedding(model_name=name, cache_dir=cache_dir)


def get_model(name: str = ""):
    """获取（必要时加载）指定模型的单例实例。

    Args:
        name: 模型名或别名；空字符串使用默认模型。

    Returns:
        FastEmbed TextEmbedding 实例
    """
    global _model, _model_name
    resolved = resolve_model_name(name)
    if _model is None or _model_name != resolved:
        with _lock:
            if _model is None or _model_name != resolved:
                _model = _load_model(resolved)
                _model_name = resolved
    return _model


def is_ready() -> bool:
    """模型是否已加载完成（供 readiness 探针使用）。"""
    return _model is not None


def embed_texts(texts: list[str], name: str = "") -> list[list[float]]:
    """对一组文本生成向量。

    Args:
        texts: 待向量化的文本列表
        name:  模型名或别名

    Returns:
        向量列表，每个元素为 float 列表
    """
    model = get_model(name)
    return [[float(x) for x in vec] for vec in model.embed(texts)]
