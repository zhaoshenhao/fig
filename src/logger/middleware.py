"""RequestID 中间件 —— 为每个 HTTP 请求生成/传递唯一标识。

核心机制:
  1. 从请求头 X-Request-ID 提取上游 ID（适用于微服务链路追踪）
  2. 若无上游 ID，则自动生成 12 位十六进制 UUID（uuid4 前 12 字节）
  3. 使用 Python ContextVar 存储 RequestID，支持异步协程上下文隔离
  4. 将 RequestID 写入响应头 X-Request-ID，确保客户端可追溯

ContextVar 说明:
  不同于 threading.local，ContextVar 在 asyncio 环境中能正确隔离并发请求——
  同一协程树共享一个 ContextVar 副本，不同请求互不干扰。
"""

from __future__ import annotations  # 推迟类型注解求值

import uuid
from contextvars import ContextVar  # Python 3.7+ 异步安全的上下文变量

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# ContextVar: 请求级上下文存储（asyncio 安全）
# ---------------------------------------------------------------------------

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
# 存储当前请求的唯一 ID，默认值为空字符串


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def get_request_id() -> str:
    """获取当前异步上下文中绑定的请求 ID。

    可在中间件下游的任何位置调用（路由处理函数、服务层、工具函数等）。

    Returns:
        当前请求的唯一标识字符串，未在中间件上下文中时返回空字符串
    """
    return _request_id_var.get()


# ---------------------------------------------------------------------------
# RequestID 中间件
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """RequestID 注入中间件 —— 为每个请求提供全链路追踪 ID。

    继承 Starlette BaseHTTPMiddleware，通过 dispatch 方法拦截请求/响应。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """拦截请求，注入 RequestID。

        执行步骤:
            1. 读取请求头 X-Request-ID（上游透传）
            2. 无上游 ID 时生成新的 uuid4 短 ID（12 位）
            3. 设置 ContextVar + request.state 双重存储
            4. 调用下游，在 finally 中重置 ContextVar（防止泄漏）
            5. 将 RequestID 写入响应头返回给客户端

        Args:
            request:  Starlette Request 对象
            call_next: 下游 ASGI 应用

        Returns:
            Starlette Response，响应头中包含 X-Request-ID
        """
        # 优先使用上游传递的 RequestID，无则自生成
        rid = request.headers.get("X-Request-ID", "") or uuid.uuid4().hex[:12]

        # 设置 ContextVar 并获取重置令牌（用于 finally 块）
        token = _request_id_var.set(rid)

        # 同时写入 request.state，方便不支持 ContextVar 的同步代码访问
        request.state.request_id = rid

        try:
            # 执行下游处理
            response = await call_next(request)
            # 将 RequestID 写入响应头，供客户端/上游关联请求
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            # 无论成功或异常，都重置 ContextVar 防止协程间的上下文泄漏
            _request_id_var.reset(token)
