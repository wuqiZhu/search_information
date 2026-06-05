# -*- coding: utf-8 -*-
"""
API 网关层

统一入口，提供：
1. 认证授权
2. 限流控制
3. 请求路由
4. 日志记录
5. 错误处理

使用方式:
    python gateway.py
    或通过 docker-compose 启动
"""

import os
import time
import logging
from datetime import datetime
from functools import wraps
from typing import Dict, Optional

from flask import Flask, request, jsonify, g
import requests

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ====== 配置 ======

# 服务端点配置
SERVICES = {
    "dashboard": {
        "url": os.environ.get("DASHBOARD_URL", "http://localhost:8085"),
        "prefix": "/",
        "auth_required": True,
    },
    "invest-frontend": {
        "url": os.environ.get("INVEST_FRONTEND_URL", "http://localhost:3000"),
        "prefix": "/invest/",
        "auth_required": True,
    },
    "invest-backend": {
        "url": os.environ.get("INVEST_BACKEND_URL", "http://localhost:5000"),
        "prefix": "/api/invest/",
        "auth_required": True,
    },
    "semantic-search": {
        "url": os.environ.get("SEMANTIC_SEARCH_URL", "http://localhost:5070"),
        "prefix": "/api/search/",
        "auth_required": True,
    },
    "notification": {
        "url": os.environ.get("NOTIFICATION_URL", "http://localhost:5050"),
        "prefix": "/api/notification/",
        "auth_required": True,
    },
}

# API 密钥配置
API_KEYS = {}
api_keys_str = os.environ.get("API_KEYS", "")
if api_keys_str:
    for pair in api_keys_str.split(","):
        if ":" in pair:
            key, name = pair.split(":", 1)
            API_KEYS[key.strip()] = name.strip()

# 限流配置
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "1000"))

# 限流存储（生产环境应使用 Redis）
rate_limit_store: Dict[str, Dict] = {}


class RateLimiter:
    """限流器"""

    @staticmethod
    def check_rate_limit(client_ip: str) -> tuple[bool, Optional[str]]:
        """
        检查限流

        Returns:
            (是否允许, 错误信息)
        """
        now = time.time()
        minute_key = f"{client_ip}:{int(now // 60)}"
        hour_key = f"{client_ip}:{int(now // 3600)}"

        # 初始化
        if minute_key not in rate_limit_store:
            rate_limit_store[minute_key] = {"count": 0, "reset_at": now + 60}
        if hour_key not in rate_limit_store:
            rate_limit_store[hour_key] = {"count": 0, "reset_at": now + 3600}

        # 检查分钟限流
        if rate_limit_store[minute_key]["count"] >= RATE_LIMIT_PER_MINUTE:
            return False, f"Rate limit exceeded: {RATE_LIMIT_PER_MINUTE} requests per minute"

        # 检查小时限流
        if rate_limit_store[hour_key]["count"] >= RATE_LIMIT_PER_HOUR:
            return False, f"Rate limit exceeded: {RATE_LIMIT_PER_HOUR} requests per hour"

        # 增加计数
        rate_limit_store[minute_key]["count"] += 1
        rate_limit_store[hour_key]["count"] += 1

        # 清理过期记录
        RateLimiter.cleanup()

        return True, None

    @staticmethod
    def cleanup():
        """清理过期的限流记录"""
        now = time.time()
        expired_keys = [
            key for key, value in rate_limit_store.items()
            if value.get("reset_at", 0) < now
        ]
        for key in expired_keys:
            del rate_limit_store[key]


def require_auth(f):
    """认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # 从 header 或 query 获取 token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.args.get('token', '')

        # 检查 API Key
        if token in API_KEYS:
            g.api_key = token
            g.client_name = API_KEYS[token]
            return f(*args, **kwargs)

        # 检查 Dashboard Token
        dashboard_token = os.environ.get("DASHBOARD_AUTH_TOKEN", "")
        if dashboard_token and token == dashboard_token:
            g.api_key = token
            g.client_name = "dashboard"
            return f(*args, **kwargs)

        return jsonify({"error": "Unauthorized", "message": "Invalid or missing API key"}), 401

    return decorated


def get_client_ip():
    """获取客户端 IP"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    return request.remote_addr


@app.before_request
def before_request():
    """请求预处理"""
    g.start_time = time.time()
    g.client_ip = get_client_ip()

    # 健康检查不记录
    if request.path == '/health':
        return

    # 限流检查
    allowed, error_msg = RateLimiter.check_rate_limit(g.client_ip)
    if not allowed:
        logger.warning(f"Rate limit exceeded for {g.client_ip}: {error_msg}")
        return jsonify({"error": "Too Many Requests", "message": error_msg}), 429

    logger.info(f"Request: {request.method} {request.path} from {g.client_ip}")


@app.after_request
def after_request(response):
    """请求后处理"""
    if hasattr(g, 'start_time'):
        duration = time.time() - g.start_time
        logger.info(f"Response: {response.status_code} ({duration:.3f}s)")

        # 添加响应头
        response.headers['X-Response-Time'] = f"{duration:.3f}s"
        response.headers['X-Request-ID'] = os.urandom(8).hex()

    return response


@app.route('/health')
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "services": {
            name: service["url"]
            for name, service in SERVICES.items()
        }
    })


@app.route('/api/services')
@require_auth
def list_services():
    """列出所有服务"""
    return jsonify({
        "services": [
            {
                "name": name,
                "prefix": service["prefix"],
                "auth_required": service["auth_required"],
            }
            for name, service in SERVICES.items()
        ]
    })


@app.route('/api/rate-limit')
@require_auth
def get_rate_limit():
    """获取限流状态"""
    client_ip = get_client_ip()
    now = time.time()
    minute_key = f"{client_ip}:{int(now // 60)}"
    hour_key = f"{client_ip}:{int(now // 3600)}"

    minute_count = rate_limit_store.get(minute_key, {}).get("count", 0)
    hour_count = rate_limit_store.get(hour_key, {}).get("count", 0)

    return jsonify({
        "client_ip": client_ip,
        "minute": {
            "limit": RATE_LIMIT_PER_MINUTE,
            "used": minute_count,
            "remaining": RATE_LIMIT_PER_MINUTE - minute_count,
        },
        "hour": {
            "limit": RATE_LIMIT_PER_HOUR,
            "used": hour_count,
            "remaining": RATE_LIMIT_PER_HOUR - hour_count,
        },
    })


def proxy_request(service_name: str, path: str):
    """代理请求到后端服务"""
    service = SERVICES.get(service_name)
    if not service:
        return jsonify({"error": "Service not found"}), 404

    # 检查认证
    if service["auth_required"]:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.args.get('token', '')

        dashboard_token = os.environ.get("DASHBOARD_AUTH_TOKEN", "")
        if not (token in API_KEYS or (dashboard_token and token == dashboard_token)):
            return jsonify({"error": "Unauthorized"}), 401

    # 构建目标 URL
    target_url = f"{service['url']}/{path}"
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"

    # 转发请求
    try:
        headers = {
            key: value
            for key, value in request.headers
            if key.lower() not in ['host', 'authorization']
        }
        headers['X-Forwarded-For'] = get_client_ip()
        headers['X-Original-Host'] = request.host

        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            timeout=30,
        )

        # 构建响应
        response = app.make_response(resp.content)
        response.status_code = resp.status_code

        # 复制响应头
        for key, value in resp.headers.items():
            if key.lower() not in ['content-length', 'transfer-encoding']:
                response.headers[key] = value

        return response

    except requests.exceptions.RequestException as e:
        logger.error(f"Proxy error: {e}")
        return jsonify({"error": "Service unavailable", "message": str(e)}), 503


# 注册路由
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    """捕获所有请求并路由到对应服务"""
    # 匹配服务
    for service_name, service in SERVICES.items():
        prefix = service["prefix"]
        if path.startswith(prefix.lstrip('/')) or (prefix == '/' and path == ''):
            # 移除前缀
            remaining_path = path[len(prefix.lstrip('/')):]
            if prefix == '/':
                remaining_path = path
            return proxy_request(service_name, remaining_path)

    return jsonify({"error": "Not found"}), 404


def create_app():
    """创建应用"""
    return app


if __name__ == '__main__':
    port = int(os.environ.get("GATEWAY_PORT", "8000"))
    host = os.environ.get("GATEWAY_HOST", "0.0.0.0")

    logger.info(f"Starting API Gateway on {host}:{port}")
    logger.info(f"Services: {list(SERVICES.keys())}")
    logger.info(f"API Keys: {len(API_KEYS)} configured")

    app.run(host=host, port=port, debug=os.environ.get("APP_DEBUG", "false").lower() == "true")
