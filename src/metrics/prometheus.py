"""Prometheus 指标模块 —— 无第三方依赖的 Prometheus 文本格式指标暴露。

本模块实现了 Counter（计数器）和 Histogram（直方图）两种核心指标类型，
并提供一个轻量级的 MetricsRegistry 注册表，以及一个自动采集 HTTP 指标的
ASGI 中间件。

设计决策:
  - 不使用 prometheus_client 库（减少依赖）
  - 手动生成符合 Prometheus Exposition Format 的文本输出
  - 线程安全：所有指标操作使用 threading.Lock 保护
  - 预注册四个内置指标:
      http_requests_total            (Counter)
      http_request_duration_seconds  (Histogram)
      llm_calls_total               (Counter)
      rag_search_duration_ms        (Histogram)

输出示例 (Prometheus text format):
  # HELP http_requests_total Counter
  # TYPE http_requests_total counter
  http_requests_total{method="GET",path="/api/chat",status="200"} 42
"""

from __future__ import annotations  # 推迟类型注解求值

import time
from collections import defaultdict
from threading import Lock  # 线程锁，保证多线程环境下指标更新的安全性

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ---------------------------------------------------------------------------
# Counter —— 单调递增计数器
# ---------------------------------------------------------------------------

class Counter:
    """Prometheus Counter 指标类型 —— 只增不减的计数器。

    典型用途:
      - http_requests_total:  HTTP 请求总数
      - llm_calls_total:      LLM API 调用次数

    线程安全:
      所有写操作均通过 threading.Lock 保护。
    """

    def __init__(self):
        """初始化计数器，内部用 defaultdict 存储 (label_key, label_value) -> value 的映射。"""
        self._lock = Lock()
        self._values: dict[tuple, float] = defaultdict(float)  # 标签组合 -> 当前计数

    def inc(self, labels: dict[str, str] | None = None) -> None:
        """计数器加 1（原子操作）。

        Args:
            labels: 可选的标签字典，如 {"method": "GET", "status": "200"}
        """
        # 将标签字典转为排序后的元组作为稳定键
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[key] += 1.0

    def collect(self, name: str) -> list[str]:
        """生成该指标的 Prometheus 文本格式输出行列表。

        Args:
            name: 指标名称（如 "http_requests_total"）

        Returns:
            Prometheus exposition format 文本行列表（含 HELP/TYPE 注释行）
        """
        lines = [f"# HELP {name} Counter", f"# TYPE {name} counter"]
        with self._lock:
            for key, val in sorted(self._values.items()):
                labels = dict(key)
                label_str = _format_labels(labels)
                lines.append(f"{name}{label_str} {val}")
        return lines


# ---------------------------------------------------------------------------
# Histogram —— 分布直方图
# ---------------------------------------------------------------------------

class Histogram:
    """Prometheus Histogram 指标类型 —— 观测值分布统计。

    典型用途:
      - http_request_duration_seconds: HTTP 请求延迟分布
      - rag_search_duration_ms:        RAG 检索耗时分布（毫秒）

    默认桶边界 (秒):
      [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    线程安全:
      所有写操作均通过 threading.Lock 保护。
    """

    def __init__(self, buckets: list[float] | None = None):
        """初始化直方图。

        Args:
            buckets: 自定义桶边界列表，不传则使用默认桶
        """
        self._lock = Lock()
        # 预定义默认桶边界（覆盖常见延迟范围）
        _default = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._buckets = sorted(buckets or _default)  # 排序确保桶边界单调递增

        # 内部存储（按标签组合分组）
        self._sums: dict[tuple, float] = defaultdict(float)        # 累计和
        self._counts: dict[tuple, int] = defaultdict(int)           # 观测次数
        self._bucket_counts: dict[tuple, dict[float, int]] = defaultdict(lambda: defaultdict(int))
        # 桶计数: (标签) -> {桶上界: 落入该桶的次数}

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        """记录一次观测值（原子操作）。

        Args:
            value:  观测到的浮点数值（如延迟秒数、耗时毫秒数）
            labels: 可选标签字典
        """
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._sums[key] += value
            self._counts[key] += 1
            # 对每个桶判断 value 是否落入
            for b in self._buckets:
                if value <= b:
                    self._bucket_counts[key][b] += 1

    def collect(self, name: str) -> list[str]:
        """生成该直方图的 Prometheus 文本格式输出。

        Prometheus 直方图输出格式:
          <name>_sum{labels} <累计和>
          <name>_count{labels} <观测次数>
          <name>_bucket{le="<上界>"} <落入计数>
          <name>_bucket{le="+Inf"} <总次数>  # 最后一个桶为无穷大

        Args:
            name: 指标名称

        Returns:
            Prometheus exposition format 文本行列表
        """
        lines = [f"# HELP {name} Histogram", f"# TYPE {name} histogram"]
        with self._lock:
            # 合并所有出现过的标签组合
            all_keys = set(self._sums) | set(self._bucket_counts)
            for key in sorted(all_keys):
                labels = dict(key)
                label_str = _format_labels(labels)

                # _sum 和 _count
                lines.append(f"{name}_sum{label_str} {self._sums.get(key, 0.0)}")
                lines.append(f"{name}_count{label_str} {self._counts.get(key, 0)}")

                # 各桶边界（le = "less than or equal"）
                for b in self._buckets:
                    le_label = _format_labels({**labels, "le": str(b)})
                    bc = self._bucket_counts.get(key, {}).get(b, 0)
                    lines.append(f"{name}_bucket{le_label} {bc}")

                # +Inf 桶（总数，必须为最后一个桶）
                le_inf_label = _format_labels({**labels, "le": "+Inf"})
                total = self._counts.get(key, 0)
                lines.append(f"{name}_bucket{le_inf_label} {total}")
        return lines


# ---------------------------------------------------------------------------
# MetricsRegistry —— 指标注册表
# ---------------------------------------------------------------------------

class MetricsRegistry:
    """全局指标注册表 —— 统一管理所有 Counter 和 Histogram 实例。

    提供懒初始化：counter() 和 histogram() 调用时按名称自动创建并缓存。
    generate_latest() 遍历所有已注册指标生成完整的 Prometheus 文本输出。
    """

    def __init__(self):
        self._metrics: dict[str, Counter | Histogram] = {}  # 指标名 -> 指标实例

    def counter(self, name: str) -> Counter:
        """获取或创建指定名称的 Counter 指标。

        Args:
            name: 指标名称

        Returns:
            Counter 实例（同名指标返回同一个实例）
        """
        if name not in self._metrics:
            self._metrics[name] = Counter()
        return self._metrics[name]  # type: ignore[return-value]

    def histogram(self, name: str, buckets: list[float] | None = None) -> Histogram:
        """获取或创建指定名称的 Histogram 指标。

        Args:
            name:    指标名称
            buckets: 桶边界列表（仅首次创建时生效）

        Returns:
            Histogram 实例（同名指标返回同一个实例）
        """
        if name not in self._metrics:
            self._metrics[name] = Histogram(buckets)
        return self._metrics[name]  # type: ignore[return-value]

    def generate_latest(self) -> str:
        """生成所有已注册指标的完整 Prometheus 文本输出。

        Returns:
            符合 Prometheus Exposition Format 的文本，
            可直接通过 /metrics 端点暴露给 Prometheus 抓取。
        """
        parts: list[str] = []
        for name in sorted(self._metrics):
            metric = self._metrics[name]
            if isinstance(metric, Counter):
                parts.extend(metric.collect(name))
            elif isinstance(metric, Histogram):
                parts.extend(metric.collect(name))
        parts.append("")  # 末尾空行，符合 Prometheus 格式要求
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# 辅助函数: 标签格式化
# ---------------------------------------------------------------------------

def _format_labels(labels: dict[str, str]) -> str:
    """将标签字典格式化为 Prometheus 标签字符串。

    Args:
        labels: 标签字典，如 {"method": "GET", "status": "200"}

    Returns:
        标签字符串，如 '{method="GET",status="200"}'，
        空字典时返回空字符串
    """
    if not labels:
        return ""
    parts = [f'{k}="{v}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


# ---------------------------------------------------------------------------
# 模块级全局注册表 & 预注册指标
# ---------------------------------------------------------------------------

_registry = MetricsRegistry()  # 全局唯一注册表实例

# 预注册核心指标，模块 import 后立即可用
http_requests_total = _registry.counter("http_requests_total")
http_request_duration_seconds = _registry.histogram("http_request_duration_seconds")
llm_calls_total = _registry.counter("llm_calls_total")
rag_search_duration_ms = _registry.histogram("rag_search_duration_ms")
# 节点/工具级指标（供 Grafana 观测各节点/工具的调用量、错误、耗时）
node_executions_total = _registry.counter("node_executions_total")
node_duration_ms = _registry.histogram(
    "node_duration_ms", buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
)
tool_calls_total = _registry.counter("tool_calls_total")
workflow_runs_total = _registry.counter("workflow_runs_total")


def record_node_metric(node: str, tool: str, status: str, duration_ms: float) -> None:
    """记录一次节点执行的 Prometheus 指标（供 DAG 引擎调用）。"""
    labels = {"node": node, "tool": tool or "none", "status": status}
    node_executions_total.inc(labels)
    tool_calls_total.inc({"tool": tool or "none", "status": status})
    node_duration_ms.observe(float(duration_ms), {"node": node, "tool": tool or "none"})


def record_workflow_run(workflow: str, status: str) -> None:
    workflow_runs_total.inc({"workflow": workflow, "status": status})


# ---------------------------------------------------------------------------
# 便捷函数: 生成 Prometheus 文本
# ---------------------------------------------------------------------------

def generate_latest() -> str:
    """生成所有指标的 Prometheus 文本输出（便捷封装）。"""
    return _registry.generate_latest()


# ---------------------------------------------------------------------------
# MetricsMiddleware —— 自动采集 HTTP 指标
# ---------------------------------------------------------------------------

class MetricsMiddleware(BaseHTTPMiddleware):
    """HTTP 指标自动采集中间件。

    对每个 HTTP 请求记录:
      - http_requests_total（按 method/path/status 标签分组计数）
      - http_request_duration_seconds（按相同标签分组统计延迟分布）

    使用方法:
      app.add_middleware(MetricsMiddleware)
    """

    async def dispatch(self, request: Request, call_next):
        """拦截请求，记录延迟和计数指标。

        Args:
            request:  Starlette Request 对象
            call_next: 下游 ASGI 处理函数

        Returns:
            下游返回的 Response 对象
        """
        start = time.time()  # 记录请求开始时间戳
        response = await call_next(request)  # 执行下游处理
        duration = time.time() - start  # 计算总延迟（秒）

        # 标签: HTTP 方法、请求路径、响应状态码
        labels = {
            "method": request.method,
            "path": request.url.path,
            "status": str(response.status_code),
        }

        # 计数器 +1
        http_requests_total.inc(labels)
        # 记录延迟分布
        http_request_duration_seconds.observe(duration, labels)

        return response
