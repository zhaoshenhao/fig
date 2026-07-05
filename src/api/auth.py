"""API 认证中间件 —— 基于静态 API Key 白名单的请求级别鉴权。

工作原理:
  1. 从请求头 X-API-Key 中提取客户端密钥
  2. 与配置中预定义的 api_keys 列表做匹配
  3. 不在白名单中的请求返回 401 Unauthorized
  4. skip_paths 中的路径前缀直接放行（如 /health, /docs 等）
  5. api_keys 列表为空时关闭鉴权（开发模式）
"""

from __future__ import annotations  # 推迟类型注解求值

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware  # ASGI 中间件基类
from starlette.responses import JSONResponse

from src.config import AuthConfig


class AuthMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件，在请求进入业务逻辑前完成鉴权。

    继承 Starlette BaseHTTPMiddleware，通过 dispatch 钩子拦截所有请求。
    """

    def __init__(self, app, config: AuthConfig):
        """初始化中间件。

        Args:
            app:    下游 ASGI 应用实例
            config: 认证配置（api_keys 白名单 + skip_paths 放行路径）
        """
        super().__init__(app)
        self._config = config  # 缓存认证配置

    async def dispatch(self, request: Request, call_next):
        """中间件入口 —— 每个 HTTP 请求到达时自动调用。

        执行流程:
            1. 白名单为空 -> 跳过鉴权（开发/调试模式）
            2. 请求路径匹配 skip_paths 前缀 -> 直接放行
            3. 校验 X-API-Key 请求头 -> 不通过返回 401
            4. 通过 -> 继续执行下游中间件和路由

        Args:
            request:  Starlette Request 对象
            call_next: 调用链中的下一个 ASGI 处理函数

        Returns:
            Response: 正常的 HTTP 响应或 401 拒绝响应
        """
        keys = self._config.api_keys
        # 无密钥列表 = 关闭鉴权，直接放行所有请求
        if not keys:
            return await call_next(request)

        # 检查是否在放行路径列表中（前缀匹配）
        path = request.url.path
        for prefix in self._config.skip_paths:
            if path.startswith(prefix):
                return await call_next(request)

        # 从请求头提取客户端提供的 API Key 并校验
        client_key = request.headers.get("X-API-Key", "")
        if client_key not in keys:
            return JSONResponse(
                status_code=401,
                content={"error": "invalid or missing X-API-Key"},
            )

        # 鉴权通过，继续后续处理
        return await call_next(request)
