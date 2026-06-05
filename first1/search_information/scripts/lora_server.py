# -*- coding: utf-8 -*-
"""
LoRA 推理服务 — 阿里云部署

百器模型第2层（榫卯层），提供精细相关评分和紧急度判断。

启动:
    python lora_server.py --port 5075 --adapters relevance_score,urgency

调用:
    curl -X POST http://localhost:5075/infer \\
      -H "Content-Type: application/json" \\
      -d '{"task":"relevance_score","data":{"title":"...","summary":"...","category":"科技"}}'
"""

import argparse
import json
import os
import signal
import sys
import time
from typing import Any, Dict

from flask import Flask, jsonify, request

# 添加项目路径（兼容不同部署位置）
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_scripts_dir))  # first1/
_trendradar_scripts = os.path.join(
    _project_root, "search_information", "TrendRadar", "scripts"
)
for _p in [_scripts_dir, _trendradar_scripts]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lora_manager import LoraManager, ADAPTER_REGISTRY

app = Flask(__name__)

# 全局变量
manager: LoraManager = None
start_time: float = 0


# ── 请求/响应 Schema ──

INFER_SCHEMA = {
    "relevance_score": {
        "required": ["title"],
        "optional": ["summary", "category"],
        "example": {
            "task": "relevance_score",
            "data": {"title": "台积电CoWoS产能翻倍", "summary": "...", "category": "科技"},
        },
    },
    "urgency": {
        "required": ["title"],
        "optional": ["platform", "rank_change"],
        "example": {
            "task": "urgency",
            "data": {"title": "A股大跌", "platform": "weibo", "rank_change": "15→3"},
        },
    },
    "sentiment_fine": {
        "required": ["title"],
        "optional": ["summary"],
        "example": {
            "task": "sentiment_fine",
            "data": {"title": "央行降准", "summary": "..."},
        },
    },
}


# ── 辅助函数 ──

def validate_infer_request(body: Dict[str, Any]) -> tuple:
    """校验请求，返回 (错误信息, 状态码)"""
    if not body:
        return {"error": "请求体为空"}, 400

    task = body.get("task")
    if not task:
        return {"error": "缺少 task 字段"}, 400

    if task not in ADAPTER_REGISTRY:
        available = list(ADAPTER_REGISTRY.keys())
        return {"error": f"未知 task: {task}，可用: {available}"}, 400

    data = body.get("data")
    if not data or not isinstance(data, dict):
        return {"error": "缺少或无效的 data 字段"}, 400

    schema = INFER_SCHEMA.get(task, {})
    for field in schema.get("required", []):
        if field not in data or not data[field]:
            return {"error": f"缺少必填字段: {field}"}, 400

    return None, 200


# ── 路由 ──

@app.route("/health", methods=["GET"])
def health():
    """健康检查"""
    if manager is None:
        return jsonify({"status": "error", "message": "服务未初始化"}), 503

    return jsonify({
        "status": "ok",
        "uptime": round(time.time() - start_time, 1),
        "current_adapter": manager.current_task,
        "available_adapters": [
            a["task"] for a in manager.list_adapters() if a["exists"]
        ],
    })


@app.route("/adapters", methods=["GET"])
def list_adapters():
    """列出所有 adapter 状态"""
    if manager is None:
        return jsonify({"error": "服务未初始化"}), 503
    return jsonify({"adapters": manager.list_adapters()})


@app.route("/infer", methods=["POST"])
def infer():
    """执行推理"""
    if manager is None:
        return jsonify({"error": "服务未初始化"}), 503

    body = request.get_json(silent=True)
    error, status = validate_infer_request(body)
    if error:
        return jsonify(error), status

    task = body["task"]
    data = body["data"]

    try:
        result = manager.infer(task, data)
        if "error" in result:
            return jsonify(result), 500

        return jsonify({
            "task": task,
            "result": result,
            "adapter": manager.current_task,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/batch_infer", methods=["POST"])
def batch_infer():
    """批量推理（同任务，多条数据）"""
    if manager is None:
        return jsonify({"error": "服务未初始化"}), 503

    body = request.get_json(silent=True)
    if not body or not body.get("task") or not body.get("items"):
        return jsonify({"error": "需要 task 和 items 字段"}), 400

    task = body["task"]
    items = body["items"]
    results = []

    for i, item in enumerate(items):
        error, status = validate_infer_request({"task": task, "data": item})
        if error:
            results.append({"index": i, "error": error["error"]})
            continue
        try:
            r = manager.infer(task, item)
            results.append({"index": i, "result": r})
        except Exception as e:
            results.append({"index": i, "error": str(e)})

    return jsonify({"task": task, "total": len(items), "results": results})


@app.route("/reload", methods=["POST"])
def reload_adapter():
    """重新加载 adapter（用于热更新训练后的新权重）"""
    if manager is None:
        return jsonify({"error": "服务未初始化"}), 503

    body = request.get_json(silent=True) or {}
    task = body.get("task")

    if task:
        ok = manager.load_adapter(task)
        if ok:
            return jsonify({"status": "ok", "message": f"adapter {task} 已重新加载"})
        return jsonify({"error": f"adapter {task} 加载失败"}), 500
    else:
        # 重新加载当前 adapter
        current = manager.current_task
        if current:
            manager.load_adapter(current)
            return jsonify({"status": "ok", "message": f"adapter {current} 已重新加载"})
        return jsonify({"error": "没有已加载的 adapter"}), 400


# ── 启动 ──

def create_app(adapters: list = None) -> Flask:
    """工厂函数（供测试用）"""
    global manager, start_time
    start_time = time.time()
    manager = LoraManager(load_on_start=adapters or [])
    return app


def main():
    parser = argparse.ArgumentParser(description="LoRA 推理服务 (百器模型第2层)")
    parser.add_argument("--port", type=int, default=5075, help="服务端口")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址")
    parser.add_argument(
        "--adapters", type=str, default="",
        help="启动时加载的 adapter (逗号分隔，如: relevance_score,urgency)"
    )
    parser.add_argument("--base-model", type=str, default=None, help="基座模型路径")
    parser.add_argument("--adapters-dir", type=str, default=None, help="adapter 根目录")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    # 环境变量覆盖
    if args.base_model:
        os.environ["LORA_BASE_MODEL"] = args.base_model
    if args.adapters_dir:
        os.environ["LORA_ADAPTERS_DIR"] = args.adapters_dir

    # 解析启动时加载的 adapter
    adapters = [a.strip() for a in args.adapters.split(",") if a.strip()]

    print(f"\n🔧 LoRA 推理服务 v1.0")
    print(f"{'='*50}")
    print(f"  端口:        {args.port}")
    print(f"  基座模型:    {os.environ.get('LORA_BASE_MODEL', '默认')}")
    print(f"  adapter 目录: {os.environ.get('LORA_ADAPTERS_DIR', '默认')}")
    print(f"  启动加载:    {adapters or '无'}")
    print(f"{'='*50}\n")

    create_app(adapters)

    # 优雅关闭
    def shutdown(sig, frame):
        print("\n🛑 正在关闭服务...")
        if manager:
            manager.unload_adapter()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
