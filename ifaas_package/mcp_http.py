"""服务器部署使用的 Streamable HTTP MCP 入口。"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from .mcp_server import create_server
from .profiles import PackingProfileClientPool


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """仅允许持有部署令牌的客户端访问 MCP。"""

    def __init__(self, app, access_token: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.access_token = access_token

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        if request.url.path == "/health":
            return await call_next(request)
        authorization = request.headers.get("authorization", "")
        if authorization != f"Bearer {self.access_token}":
            return JSONResponse({"code": "UNAUTHORIZED", "message": "无效的 MCP 访问令牌"}, 401)
        return await call_next(request)


def create_http_app() -> Starlette:
    """创建可由 Uvicorn 或其他 ASGI Server 托管的应用。"""

    access_token = os.environ.get("IFAAS_MCP_ACCESS_TOKEN", "").strip()
    if not access_token:
        raise RuntimeError("必须设置 IFAAS_MCP_ACCESS_TOKEN，拒绝启动未鉴权的远程 MCP")

    allowed_hosts = [
        item.strip()
        for item in os.environ.get("IFAAS_MCP_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    ]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(allowed_hosts),
        allowed_hosts=allowed_hosts,
    )
    manager = StreamableHTTPSessionManager(
        create_server(profile_pool=PackingProfileClientPool.from_environment()),
        stateless=True,
        json_response=True,
        security_settings=security,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "ifaas-package-mcp"})

    return Starlette(
        routes=[Route("/health", health), Mount("/mcp", app=manager.handle_request)],
        middleware=[Middleware(BearerTokenMiddleware, access_token=access_token)],
        lifespan=lifespan,
    )


def main() -> None:
    host = os.environ.get("IFAAS_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("IFAAS_MCP_PORT", "36003"))
    uvicorn.run(create_http_app(), host=host, port=port)


if __name__ == "__main__":
    main()
