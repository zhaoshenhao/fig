"""
向量检索工具模块 (RAG Search)

负责在 Qdrant 向量数据库中执行混合检索（稠密向量 + 稀疏 BM25），
将检索到的文档片段拼接为上下文文本，供下游 LLM 节点使用。

检索流程：
1. 将用户查询通过 Ollama 嵌入模型转为稠密向量
2. 在指定（或自动检测）的 Qdrant 集合中执行混合搜索
3. 按分数降序排列所有结果，取前 N 条
4. 拼接所有文档片段的 text 字段为上下文

典型配置字段（config dict）：
    - embed_provider (str): 嵌入模型供应商名称
    - collection (str | list[str], 可选): 目标集合名称，为空时自动根据工作流名解析
    - limit (int): 返回的最大文档数，默认 10
    - score_threshold (float, 可选): 最低分数阈值，用于过滤低质量结果
    - prefetch_limit (int): 预取数量（用于 RRF 融合前的候选集大小），默认 20
"""

import time

from src.config import get_app_config
from src.metrics.prometheus import rag_search_duration_ms
from src.session.data import SessionData

_embed_client = None
_embed_provider_key = None
_qdrant = None


def rag_search(config: dict, session: SessionData) -> dict:
    """
    执行一次 RAG 向量检索。

    步骤：
    1. 通过嵌入模型将用户查询 (session.current_query) 转为向量
    2. 解析目标 Qdrant 集合列表
    3. 在每个集合中执行混合搜索（稠密 + 稀疏，RRF 融合）
    4. 合并所有集合的结果，按分数降序排序，截取前 N 条
    5. 提取文档片段的 text 并拼接为上下文字符串

    Args:
        config (dict): 节点配置字典，包含以下字段：
            - embed_provider (str, 可选): 嵌入模型供应商名称
            - collection (str | list[str], 可选): 目标集合，指定为字符串或列表
            - limit (int, 可选): 返回的最大文档数，默认 10
            - score_threshold (float, 可选): 最低分数阈值
            - prefetch_limit (int, 可选): 混合检索预取数量，默认 20
        session (SessionData): 当前会话数据，主要使用 current_query

    Returns:
        dict: 包含以下键的字典：
            - text (str): 拼接后的上下文字符串，格式为 "\n\n".join(chunks)
            - chunks (list[str]): 各文档片段的文本列表
            - results (list[dict]): 原始检索结果列表，每个元素包含 payload 和 score
    """
    # 延迟导入，避免循环依赖：LLMClient 用于嵌入模型调用，QdrantSearch 用于向量检索
    from src.llm.client import LLMClient
    from src.rag.qdrant import QdrantSearch

    # 记录检索开始时间，用于计算耗时指标
    t0 = time.time()
    app = get_app_config()

    # 获取嵌入模型供应商配置
    provider = app.embed_provider(config.get("embed_provider", ""))
    query = session.current_query

    # 复用 LLMClient 和 QdrantSearch，避免每次创建连接
    global _embed_client, _embed_provider_key, _qdrant
    provider_key = f"{provider.base_url}:{provider.model}"
    if _embed_client is None or _embed_provider_key != provider_key:
        from src.llm.client import LLMClient
        _embed_client = LLMClient(base_url=provider.base_url, api_key=provider.api_key)
        _embed_provider_key = provider_key
    if _qdrant is None:
        from src.rag.qdrant import QdrantSearch
        _qdrant = QdrantSearch()

    vectors = _embed_client.embed(provider.model, query)
    vector = vectors[0]

    # 解析目标集合列表（支持单个集合字符串、列表，或自动检测）
    collections = _resolve_collections(config, session)

    all_results = []
    for col in collections:
        try:
            # 执行混合搜索：稠密向量 + 稀疏 BM25，RRF 融合
            results = _qdrant.search(
                collection=col,
                vector=vector,
                query_text=query,
                limit=config.get("limit", 10),
                score_threshold=config.get("score_threshold"),
                prefetch_limit=config.get("prefetch_limit", 20),
            )
            # 将当前集合的检索结果合并到总结果列表
            all_results.extend(results)
        except Exception:
            # 单个集合检索失败时静默跳过，不中断其他集合的检索
            # 这是容错设计：某个集合可能不存在或暂时不可用
            continue

    # 按分数降序排列所有结果（分数越高表示相关性越强）
    all_results.sort(key=lambda r: r.get("score", 0), reverse=True)
    # 截取前 limit 条结果（config 中指定或默认 10）
    limit = config.get("limit", 10)
    all_results = all_results[:limit]

    # 提取每个结果的 text 字段（存储在 Qdrant payload 中）
    chunks = [r["payload"].get("text", "") for r in all_results]
    # 将多个文档片段拼接为上下文字符串，以双换行分隔
    context = "\n\n".join(chunks)

    # 记录 RAG 检索耗时（毫秒）
    rag_search_duration_ms.observe((time.time() - t0) * 1000)

    return {"text": context, "chunks": chunks, "results": all_results}


def _resolve_collections(config: dict, session: SessionData) -> list[str]:
    """
    解析要检索的 Qdrant 集合名称列表。

    解析优先级：
    1. 如果 config 中指定了 "collection" 字段（字符串或列表），直接使用
    2. 否则，根据当前工作流名称从全局配置中查找关联的集合列表
    3. 如果都解析失败，返回默认集合 ["default"]

    Args:
        config (dict): 节点配置字典，可能包含 "collection" 键
        session (SessionData): 当前会话数据，通过 _workflow 字段获取工作流名

    Returns:
        list[str]: 集合名称列表（至少包含一个元素）
    """
    col = config.get("collection")
    # 情况1：未指定集合，尝试自动根据工作流名解析
    if col is None:
        app = get_app_config()
        wf_name = session._workflow
        if wf_name:
            try:
                # 从全局配置中获取该工作流关联的集合列表
                return app.wf_collections(wf_name)
            except KeyError:
                # 工作流名在配置中不存在，静默回退到默认集合
                pass
        return ["default"]
    # 情况2：config 中指定了集合列表
    if isinstance(col, list):
        return col
    # 情况3：config 中指定了单个集合名称（字符串），包装为列表返回
    return [col]
