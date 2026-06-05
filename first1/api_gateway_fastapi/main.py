# -*- coding: utf-8 -*-
"""
FastAPI API 网关

高性能异步 API 网关，替代 Flask 版本。

特性：
1. 异步处理（更高并发）
2. 自动 API 文档（Swagger/ReDoc）
3. 请求验证（Pydantic）
4. 依赖注入
5. 中间件支持

使用方式:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import time
import logging
from datetime import datetime
from typing import Dict, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from pydantic import BaseModel

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ====== 配置模型 ======

class ServiceConfig(BaseModel):
    """服务配置"""
    url: str
    prefix: str
    auth_required: bool = True
    timeout: int = 30


class GatewayConfig(BaseModel):
    """网关配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000


# ====== 服务配置 ======

SERVICES: Dict[str, ServiceConfig] = {
    "dashboard": ServiceConfig(
        url=os.environ.get("DASHBOARD_URL", "http://localhost:8085"),
        prefix="/",
        auth_required=True,
    ),
    "invest-frontend": ServiceConfig(
        url=os.environ.get("INVEST_FRONTEND_URL", "http://localhost:3000"),
        prefix="/invest/",
        auth_required=True,
    ),
    "invest-backend": ServiceConfig(
        url=os.environ.get("INVEST_BACKEND_URL", "http://localhost:5000"),
        prefix="/api/invest/",
        auth_required=True,
    ),
    "semantic-search": ServiceConfig(
        url=os.environ.get("SEMANTIC_SEARCH_URL", "http://localhost:5070"),
        prefix="/api/search/",
        auth_required=True,
    ),
    "notification": ServiceConfig(
        url=os.environ.get("NOTIFICATION_URL", "http://localhost:5050"),
        prefix="/api/notification/",
        auth_required=True,
    ),
}

# API 密钥配置
API_KEYS: Dict[str, str] = {}
api_keys_str = os.environ.get("API_KEYS", "")
if api_keys_str:
    for pair in api_keys_str.split(","):
        if ":" in pair:
            key, name = pair.split(":", 1)
            API_KEYS[key.strip()] = name.strip()

# Dashboard Token
DASHBOARD_TOKEN = os.environ.get("DASHBOARD_AUTH_TOKEN", "")


# ====== 限流器 ======

class RateLimiter:
    """异步限流器"""

    def __init__(self, max_per_minute: int = 60, max_per_hour: int = 1000):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self.minute_store: Dict[str, Dict] = {}
        self.hour_store: Dict[str, Dict] = {}

    async def check(self, client_ip: str) -> tuple[bool, Optional[str]]:
        """检查限流"""
        now = time.time()
        minute_key = f"{client_ip}:{int(now // 60)}"
        hour_key = f"{client_ip}:{int(now // 3600)}"

        # 初始化
        if minute_key not in self.minute_store:
            self.minute_store[minute_key] = {"count": 0, "reset_at": now + 60}
        if hour_key not in self.hour_store:
            self.hour_store[hour_key] = {"count": 0, "reset_at": now + 3600}

        # 检查分钟限流
        if self.minute_store[minute_key]["count"] >= self.max_per_minute:
            return False, f"Rate limit exceeded: {self.max_per_minute} requests per minute"

        # 检查小时限流
        if self.hour_store[hour_key]["count"] >= self.max_per_hour:
            return False, f"Rate limit exceeded: {self.max_per_hour} requests per hour"

        # 增加计数
        self.minute_store[minute_key]["count"] += 1
        self.hour_store[hour_key]["count"] += 1

        # 清理过期记录
        self._cleanup()

        return True, None

    def _cleanup(self):
        """清理过期记录"""
        now = time.time()
        self.minute_store = {
            k: v for k, v in self.minute_store.items()
            if v.get("reset_at", 0) > now
        }
        self.hour_store = {
            k: v for k, v in self.hour_store.items()
            if v.get("reset_at", 0) > now
        }


# ====== 应用生命周期 ======

rate_limiter = RateLimiter()
http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global http_client

    # 启动时
    logger.info("Starting API Gateway...")
    http_client = httpx.AsyncClient(timeout=30.0)
    logger.info(f"Services: {list(SERVICES.keys())}")
    logger.info(f"API Keys: {len(API_KEYS)} configured")

    yield

    # 关闭时
    if http_client:
        await http_client.aclose()
    logger.info("API Gateway stopped")


# ====== 创建应用 ======

app = FastAPI(
    title="Investment System API Gateway",
    description="统一 API 网关，提供认证、限流、路由功能",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====== 依赖注入 ======

def get_client_ip(request: Request) -> str:
    """获取客户端 IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def verify_auth(request: Request) -> str:
    """验证认证"""
    # 从 header 获取 token
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""

    # 从 query 获取 token
    if not token:
        token = request.query_params.get("token", "")

    # 检查 API Key
    if token in API_KEYS:
        return API_KEYS[token]

    # 检查 Dashboard Token
    if DASHBOARD_TOKEN and token == DASHBOARD_TOKEN:
        return "dashboard"

    raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing API key")


# ====== 中间件 ======

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """添加处理时间头"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}"
    return response


# ====== 路由 ======

@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "services": {name: service.url for name, service in SERVICES.items()},
    }


@app.get("/api/services")
async def list_services(client_name: str = Depends(verify_auth)):
    """列出所有服务"""
    return {
        "services": [
            {
                "name": name,
                "prefix": service.prefix,
                "auth_required": service.auth_required,
            }
            for name, service in SERVICES.items()
        ]
    }


@app.get("/api/rate-limit")
async def get_rate_limit(
    request: Request,
    client_name: str = Depends(verify_auth),
):
    """获取限流状态"""
    client_ip = get_client_ip(request)
    now = time.time()
    minute_key = f"{client_ip}:{int(now // 60)}"
    hour_key = f"{client_ip}:{int(now // 3600)}"

    minute_count = rate_limiter.minute_store.get(minute_key, {}).get("count", 0)
    hour_count = rate_limiter.hour_store.get(hour_key, {}).get("count", 0)

    return {
        "client_ip": client_ip,
        "minute": {
            "limit": rate_limiter.max_per_minute,
            "used": minute_count,
            "remaining": rate_limiter.max_per_minute - minute_count,
        },
        "hour": {
            "limit": rate_limiter.max_per_hour,
            "used": hour_count,
            "remaining": rate_limiter.max_per_hour - hour_count,
        },
    }


async def proxy_request(
    request: Request,
    service_name: str,
    path: str,
) -> Response:
    """代理请求到后端服务"""
    service = SERVICES.get(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # 检查认证
    if service.auth_required:
        try:
            verify_auth(request)
        except HTTPException:
            raise

    # 检查限流
    client_ip = get_client_ip(request)
    allowed, error_msg = await rate_limiter.check(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=error_msg)

    # 构建目标 URL
    target_url = f"{service.url}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    # 转发请求
    try:
        headers = dict(request.headers)
        headers.pop("host", None)
        headers["X-Forwarded-For"] = client_ip
        headers["X-Original-Host"] = request.headers.get("host", "")

        body = await request.body()

        response = await http_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            timeout=service.timeout,
        )

        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
        )

    except httpx.RequestError as e:
        logger.error(f"Proxy error: {e}")
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")


# 通配符路由
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def catch_all(request: Request, path: str):
    """捕获所有请求并路由到对应服务"""
    # 匹配服务
    for service_name, service in SERVICES.items():
        prefix = service.prefix.lstrip("/")
        if path.startswith(prefix) or (service.prefix == "/" and path == ""):
            remaining_path = path[len(prefix):]
            if service.prefix == "/":
                remaining_path = path
            return await proxy_request(request, service_name, remaining_path)

    raise HTTPException(status_code=404, detail="Not found")


# ====== 启动 ======

if __name__ == "__main__":
    import uvicorn

    config = GatewayConfig(
        host=os.environ.get("GATEWAY_HOST", "0.0.0.0"),
        port=int(os.environ.get("GATEWAY_PORT", "8000")),
        debug=os.environ.get("APP_DEBUG", "false").lower() == "true",
    )

    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
    )
