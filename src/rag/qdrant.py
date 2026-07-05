"""Qdrant 向量检索模块 —— 封装 Qdrant 客户端的所有核心操作。

核心能力:
  1. 集合管理: ensure_collection —— 自动创建向量索引 + BM25 稀疏索引
  2. 向量写入: upsert —— 批量写入向量点（Dense + Sparse）
  3. 混合检索: search —— 支持 Dense Vector + Sparse BM25 + RRF 融合，
     也支持纯向量检索（无查询文本时）和纯关键词检索（无向量时）
  4. 分页遍历: scroll —— 翻页浏览集合内容（用于 Streamlit 只读 GUI）
  5. 计数查询: count —— 返回集合文档总数

混合检索策略 (RRF):
  - Dense 向量检索（Cosine 相似度） + Sparse BM25 关键词检索
  - 使用 Qdrant RRF (Reciprocal Rank Fusion) 进行分数融合
  - 不需要独立 Rerank 服务，零额外依赖
  - 当同时提供 vector 和 query_text 时，优先尝试混合检索；
    若混合检索失败（如集合未配置 sparse），自动降级为纯向量检索

Qdrant 连接:
  - 始终使用 gRPC (prefer_grpc=True)，性能优于 HTTP
"""

from qdrant_client import QdrantClient  # Qdrant 官方 Python 客户端
from qdrant_client.models import (
    Distance,  # 向量距离度量: Cosine / Euclid / Dot
    Filter,  # 查询过滤条件
    Fusion,  # 融合策略: RRF (Reciprocal Rank Fusion)
    FusionQuery,  # 融合查询体
    Modifier,  # 稀疏向量权重修饰器: IDF 归一化
    PointStruct,  # 向量点结构体 (id + vector + payload)
    Prefetch,  # 预取查询体（混合检索中的独立查询分支）
    SparseIndexParams,  # 稀疏向量索引参数
    SparseVectorParams,  # 稀疏向量配置参数
    VectorParams,  # 稠密向量配置参数 (size + distance)
)


class QdrantSearch:
    """Qdrant 检索门面 —— 对 QdrantClient 的常用操作做了一层薄封装。

    所有方法均委托给底层 gRPC 客户端，本类的职责是:
      - 封装集合创建时的一致默认值（Dense 768d Cosine + Sparse BM25 IDF）
      - 统一异常降级策略（混合检索失败 -> 纯向量检索）
      - 标准化返回值格式（dict 列表）
    """

    def __init__(self, host: str = "localhost", port: int = 6334):
        """初始化 Qdrant 客户端连接。

        Args:
            host: Qdrant 服务主机地址
            port: gRPC 端口（默认 6334）
        """
        self._client = QdrantClient(host=host, port=port, prefer_grpc=True)

    # ------------------------------------------------------------------
    # 集合管理
    # ------------------------------------------------------------------

    def ensure_collection(self, name: str, vector_size: int = 768):
        """确保指定集合存在，不存在则自动创建。

        创建的集合同时支持:
          - Dense 向量索引: 维度 vector_size，Cosine 距离度量
          - Sparse 向量索引: BM25 关键词检索，IDF 权重修饰

        幂等操作：集合已存在时直接返回。

        Args:
            name:        集合名称
            vector_size: Dense 向量的维度（需与 Embedding 模型输出匹配）
        """
        if self._client.collection_exists(name):
            return
        self._client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,  # Cosine 相似度，适用于文本语义检索
            ),
            sparse_vectors_config={
                # 稀疏向量 "bm25": 用于关键词全文检索
                "bm25": SparseVectorParams(
                    index=SparseIndexParams(),       # 默认索引参数
                    modifier=Modifier.IDF,           # IDF 权重修饰（降低常见词权重）
                ),
            },
        )

    # ------------------------------------------------------------------
    # 向量写入
    # ------------------------------------------------------------------

    def upsert(self, collection: str, points: list[dict]):
        """批量写入或更新向量点。

        每个 point 字典需包含:
          - id:      唯一标识（int 或 UUID 字符串）
          - vector:  Dense 向量（list[float]），键为 "" 表示默认向量
          - payload: 可选，附加元数据字典

        Args:
            collection: 目标集合名称
            points:     向量点字典列表
        """
        self._client.upsert(
            collection_name=collection,
            points=[
                PointStruct(
                    id=p["id"],
                    vector={"": p["vector"]},  # "" 键 = 默认稠密向量
                    payload=p.get("payload", {}),
                )
                for p in points
            ],
        )

    # ------------------------------------------------------------------
    # 检索查询
    # ------------------------------------------------------------------

    def search(
        self,
        collection: str,
        vector: list[float],
        query_text: str = "",
        limit: int = 10,
        offset: int = 0,
        score_threshold: float | None = None,
        prefetch_limit: int = 20,
        filter: dict | None = None,
    ) -> list[dict]:
        """统一检索入口 —— 自动选择混合检索或纯向量检索。

        策略:
          - 如果提供了 query_text（非空），尝试混合检索（Dense + BM25 + RRF）
          - 如果混合检索失败（异常），自动降级为纯向量检索
          - 如果没有提供 query_text，直接使用纯向量检索

        返回值格式:
          [{"id": ..., "score": ..., "payload": {...}}, ...]

        Args:
            collection:      集合名称
            vector:          Dense 查询向量
            query_text:      查询文本（用于 BM25 稀疏检索，空字符串表示不启用）
            limit:           返回的最大结果数
            offset:          分页偏移量
            score_threshold: 最低分数阈值（仅纯向量检索时生效，None = 不限制）
            prefetch_limit:  混合检索时每个分支的预取数量
            filter:          自定义过滤条件字典（转译为 Qdrant Filter）

        Returns:
            检索结果列表，按 score 降序排列
        """
        # 将自定义 dict 格式的 filter 转译为 Qdrant Filter 对象
        qdrant_filter = _build_filter(filter) if filter else None

        # 如果有查询文本，尝试混合检索
        if query_text:
            try:
                return self._search_hybrid(
                    collection, vector, query_text, limit, offset,
                    prefetch_limit, qdrant_filter,
                )
            except Exception:
                # 混合检索失败时静默降级为纯向量检索
                # 常见原因: 集合未配置 sparse 向量索引
                pass

        # 纯向量检索（默认/降级路径）
        return self._search_vector(
            collection, vector, limit, offset, score_threshold, qdrant_filter,
        )

    def _search_vector(
        self,
        collection: str,
        vector: list[float],
        limit: int,
        offset: int,
        score_threshold: float | None,
        qdrant_filter: Filter | None = None,
    ) -> list[dict]:
        """纯 Dense 向量检索（Cosine 相似度）。

        使用 Qdrant query_points API（非旧版 search API），
        直接传入向量作为 query 参数。
        """
        results = self._client.query_points(
            collection_name=collection,
            query=vector,                     # Dense 查询向量
            limit=limit,
            offset=offset,
            score_threshold=score_threshold,  # 最低分数过滤
            query_filter=qdrant_filter,       # 元数据过滤条件
        )
        return [
            {"id": r.id, "score": r.score, "payload": r.payload}
            for r in results.points
        ]

    def _search_hybrid(
        self,
        collection: str,
        vector: list[float],
        query_text: str,
        limit: int,
        offset: int,
        prefetch_limit: int,
        qdrant_filter: Filter | None = None,
    ) -> list[dict]:
        """混合检索 —— Dense 向量 + Sparse BM25，RRF 分数融合。

        检索流程:
          1. Prefetch 阶段: 同时发起两个独立查询
             - 分支 1: Dense 向量检索 (using=""，默认向量字段)
             - 分支 2: Sparse BM25 关键词检索 (using="bm25")
          2. Fusion 阶段: 使用 RRF 算法融合两路结果的排序
          3. 应用 limit/offset 分页和全局 filter

        RRF 的优势:
          - 无需训练或调参，算法级融合
          - 天然融合语义匹配和关键词匹配
          - 对分数尺度不一致的两路结果能公平融合
        """
        # 构建两路预取查询
        prefetch = [
            Prefetch(
                query=vector,                    # Dense 检索分支
                limit=prefetch_limit,            # 预取数量（通常 > limit）
                using="",                        # 使用默认稠密向量
                filter=qdrant_filter,
            ),
            Prefetch(
                query=query_text,                # BM25 关键词检索分支
                limit=prefetch_limit,
                using="bm25",                    # 使用稀疏向量 "bm25"
                filter=qdrant_filter,
            ),
        ]

        # 执行融合查询
        results = self._client.query_points(
            collection_name=collection,
            prefetch=prefetch,
            query=FusionQuery(fusion=Fusion.RRF),  # RRF 融合
            limit=limit,
            query_filter=qdrant_filter,
        )
        return [
            {"id": r.id, "score": r.score, "payload": r.payload}
            for r in results.points
        ]

    # ------------------------------------------------------------------
    # 分页浏览 (Scroll)
    # ------------------------------------------------------------------

    def scroll(
        self,
        collection: str,
        limit: int = 20,
        offset: int = 0,
        filter: dict | None = None,
    ) -> tuple[list[dict], int | None]:
        """分页遍历集合中的点（用于 Streamlit 只读浏览）。

        Qdrant scroll 基于 offset 游标分页，不保证总数一致（类似 MongoDB skip）。
        适用于只读 GUI 翻页场景。

        Args:
            collection: 集合名称
            limit:      每页返回的最大点数
            offset:     游标偏移量（起始或上一页返回的 next_offset）
            filter:     可选的元数据过滤条件

        Returns:
            (results, next_offset):
              results:     点列表 [{"id": ..., "payload": {...}}, ...]
              next_offset: 下一页的游标值，None 表示已到末尾
        """
        qdrant_filter = _build_filter(filter) if filter else None
        records, next_offset = self._client.scroll(
            collection_name=collection,
            limit=limit,
            offset=offset,
            with_payload=True,         # 同时返回 payload 元数据
            scroll_filter=qdrant_filter,
        )
        results = [
            {"id": r.id, "payload": r.payload}
            for r in records
        ]
        if next_offset is None:
            return results, None
        if isinstance(next_offset, int):
            return results, next_offset
        return results, next_offset.to_int()

    def scroll_with_filter(
        self,
        collection: str,
        limit: int = 20,
        offset: int = 0,
        filter: dict | None = None,
    ) -> tuple[list[dict], int | None]:
        """带过滤条件的分页浏览 —— 与 scroll 等价，命名更明确。"""
        return self.scroll(collection, limit=limit, offset=offset, filter=filter)

    # ------------------------------------------------------------------
    # 计数
    # ------------------------------------------------------------------

    def count(self, collection: str, filter: dict | None = None) -> int:
        """统计集合中的文档总数（支持过滤条件）。

        Args:
            collection: 集合名称
            filter:     可选过滤条件

        Returns:
            符合条件的文档数量
        """
        qdrant_filter = _build_filter(filter) if filter else None
        result = self._client.count(
            collection_name=collection, count_filter=qdrant_filter,
        )
        return result.count

    # ------------------------------------------------------------------
    # 知识库管理
    # ------------------------------------------------------------------

    def list_collections(self) -> list[str]:
        """列出所有集合名称。"""
        collections = self._client.get_collections()
        return [c.name for c in collections.collections]

    def collection_info(self, name: str) -> dict:
        """获取集合详情 —— 点数、向量维度、索引配置等。

        Args:
            name: 集合名称

        Returns:
            {
                "name": str,
                "points_count": int,
                "indexed_vectors_count": int,
                "segments_count": int,
                "config": dict (params / hnsw_config / optimizers_config),
            }
        """
        info = self._client.get_collection(name)
        config_info: dict = {}
        if info.config.params.vectors:
            config_info["vectors"] = {
                "size": info.config.params.vectors.size,
                "distance": str(info.config.params.vectors.distance),
            }
        return {
            "name": name,
            "points_count": info.points_count or 0,
            "indexed_vectors_count": info.indexed_vectors_count or 0,
            "segments_count": info.segments_count or 0,
            "status": str(info.status) if info.status else "unknown",
            "config": config_info,
        }

    def delete_collection(self, name: str) -> bool:
        """删除整个集合。

        Args:
            name: 集合名称

        Returns:
            True 表示删除成功
        """
        self._client.delete_collection(name)
        return True

    def delete_points(self, collection: str, point_ids: list[int]) -> dict:
        """按 ID 列表删除集合中的点。

        Args:
            collection: 集合名称
            point_ids:  要删除的点 ID 列表

        Returns:
            {"deleted": int, "status": "completed"}
        """
        from qdrant_client.models import PointIdsList

        result = self._client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=point_ids),
        )
        return {
            "deleted": len(point_ids),
            "status": str(result.status),
        }


# ---------------------------------------------------------------------------
# 辅助函数: 将自定义 dict filter 转译为 Qdrant Filter 对象
# ---------------------------------------------------------------------------

def _build_filter(filter_dict: dict) -> Filter:
    """将简化 dict 格式的过滤条件转译为 Qdrant Filter 对象。

    支持的过滤语法:
      {"key": "value"}                     -> 精确匹配 (MatchValue)
      {"key": {"match": "value"}}          -> 显式精确匹配
      {"key": {"range": {"gte": 0.5}}}    -> 范围过滤 (Range)

    多个条件以 AND 逻辑组合（must 语义）。

    Args:
        filter_dict: 自定义过滤条件字典

    Returns:
        Qdrant Filter 对象，空字典返回空 Filter（不匹配任何条件）
    """
    from qdrant_client.models import FieldCondition, MatchValue, Range

    must = []  # AND 条件列表
    for key, value in filter_dict.items():
        if isinstance(value, dict):
            # 子字典: 支持 match / range 等操作符
            for op_key, op_value in value.items():
                if op_key == "match":
                    must.append(
                        FieldCondition(key=key, match=MatchValue(value=op_value))
                    )
                elif op_key == "range":
                    must.append(
                        FieldCondition(key=key, range=Range(**op_value))
                    )
        else:
            # 普通值: 默认精确匹配
            must.append(
                FieldCondition(key=key, match=MatchValue(value=value))
            )

    # 空 must 列表 = 无过滤条件；返回空 Filter 表示不做任何限制
    return Filter(must=must) if must else Filter()
