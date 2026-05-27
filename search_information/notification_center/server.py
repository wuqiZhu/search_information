"""统一通知中心服务

HTTP API 服务，所有项目通过 POST /notify 发送通知。
支持优先级调度、消息聚合、多渠道推送。

使用方式：
    python -m notification_center.server
    # 或
    flask --app notification_center.server run --port 5050
"""

import os
import json
import time
import hashlib
import hmac
import base64
import urllib.parse
import urllib.request
import logging
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("请安装 Flask: pip install flask")
    raise

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 优先级定义
PRIORITY_URGENT = 0    # 紧急：立即推送
PRIORITY_HIGH = 1      # 高：实时推送
PRIORITY_MEDIUM = 2    # 中：每小时聚合推送
PRIORITY_LOW = 3       # 低：每天汇总推送

PRIORITY_NAMES = {
    PRIORITY_URGENT: "urgent",
    PRIORITY_HIGH: "high",
    PRIORITY_MEDIUM: "medium",
    PRIORITY_LOW: "low",
}

# 消息队列
message_queue = defaultdict(list)  # priority -> [messages]
queue_lock = threading.Lock()

# 聚合消息缓存
aggregated_cache = defaultdict(list)  # hour_key -> [messages]
last_aggregated_hour = None

# 配置
config = {
    "dingtalk_webhook": os.environ.get("DINGTALK_WEBHOOK", ""),
    "dingtalk_secret": os.environ.get("DINGTALK_SECRET", ""),
    "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
    "quiet_hours_start": int(os.environ.get("QUIET_HOURS_START", "23")),
    "quiet_hours_end": int(os.environ.get("QUIET_HOURS_END", "7")),
    "aggregate_interval_minutes": int(os.environ.get("AGGREGATE_INTERVAL", "60")),
}


def is_quiet_hours() -> bool:
    """检查是否在安静时段"""
    hour = datetime.now().hour
    start = config["quiet_hours_start"]
    end = config["quiet_hours_end"]
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


def send_dingtalk(text: str, title: str = "通知"):
    """发送钉钉消息"""
    webhook = config["dingtalk_webhook"]
    secret = config["dingtalk_secret"]
    if not webhook:
        logger.warning("DINGTALK_WEBHOOK 未配置")
        return False

    try:
        if secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                secret.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                digestmod=hashlib.sha256
            ).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            url = f"{webhook}&timestamp={timestamp}&sign={sign}"
        else:
            url = webhook

        payload = json.dumps({
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text}
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('errcode') == 0
    except Exception as e:
        logger.error(f"钉钉发送失败: {e}")
        return False


def send_telegram(text: str):
    """发送 Telegram 消息"""
    token = config["telegram_bot_token"]
    chat_id = config["telegram_chat_id"]
    if not token or not chat_id:
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('ok', False)
    except Exception as e:
        logger.error(f"Telegram 发送失败: {e}")
        return False


def dispatch_message(text: str, title: str = "通知", channel: str = "dingtalk"):
    """分发消息到指定渠道"""
    if channel == "dingtalk":
        return send_dingtalk(text, title)
    elif channel == "telegram":
        return send_telegram(text)
    else:
        logger.error(f"不支持的通知渠道: {channel}")
        return False


def process_immediate(message: dict):
    """立即推送消息"""
    text = message.get("text", "")
    title = message.get("title", "通知")
    channel = message.get("channel", "dingtalk")
    return dispatch_message(text, title, channel)


def process_aggregated():
    """处理聚合消息"""
    global last_aggregated_hour

    now = datetime.now()
    current_hour = now.strftime("%Y-%m-%d %H")

    with queue_lock:
        if current_hour == last_aggregated_hour:
            return

        messages = aggregated_cache.pop(current_hour, [])
        last_aggregated_hour = current_hour

    if not messages:
        return

    lines = [f"## 📊 定时汇总 ({now.strftime('%H:%M')})", ""]
    by_source = defaultdict(list)
    for msg in messages:
        source = msg.get("source", "未知")
        by_source[source].append(msg)

    for source, msgs in by_source.items():
        lines.append(f"### {source} ({len(msgs)}条)")
        for msg in msgs[:5]:
            lines.append(f"- {msg.get('title', msg.get('text', '')[:50])}")
        if len(msgs) > 5:
            lines.append(f"- ...还有 {len(msgs) - 5} 条")
        lines.append("")

    text = "\n".join(lines)
    dispatch_message(text, "定时汇总", "dingtalk")


def background_worker():
    """后台工作线程"""
    while True:
        try:
            now = datetime.now()
            if not is_quiet_hours():
                if now.minute == 0:
                    process_aggregated()
        except Exception as e:
            logger.error(f"后台工作线程异常: {e}")
        time.sleep(60)


# API 路由

@app.route('/notify', methods=['POST'])
def notify():
    """
    发送通知

    请求体：
    {
        "text": "通知内容（支持Markdown）",
        "title": "通知标题",
        "priority": "urgent|high|medium|low",
        "source": "来源项目名",
        "channel": "dingtalk|telegram",
        "tags": ["标签1", "标签2"]
    }
    """
    data = request.json
    if not data:
        return jsonify({"error": "请求体不能为空"}), 400

    text = data.get("text", "")
    if not text:
        return jsonify({"error": "text 不能为空"}), 400

    priority_name = data.get("priority", "high")
    priority = {"urgent": PRIORITY_URGENT, "high": PRIORITY_HIGH,
                "medium": PRIORITY_MEDIUM, "low": PRIORITY_LOW}.get(priority_name, PRIORITY_HIGH)

    message = {
        "text": text,
        "title": data.get("title", "通知"),
        "priority": priority,
        "source": data.get("source", "未知"),
        "channel": data.get("channel", "dingtalk"),
        "tags": data.get("tags", []),
        "timestamp": datetime.now().isoformat(),
    }

    # 紧急和高优先级立即推送
    if priority <= PRIORITY_HIGH:
        if is_quiet_hours() and priority > PRIORITY_URGENT:
            with queue_lock:
                aggregated_cache[datetime.now().strftime("%Y-%m-%d %H")].append(message)
            return jsonify({"status": "queued", "reason": "quiet_hours"}), 200

        success = process_immediate(message)
        return jsonify({"status": "sent" if success else "failed"}), 200

    # 中低优先级聚合推送
    hour_key = datetime.now().strftime("%Y-%m-%d %H")
    with queue_lock:
        aggregated_cache[hour_key].append(message)
    return jsonify({"status": "queued", "aggregate_hour": hour_key}), 200


@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "config": {
            "dingtalk_configured": bool(config["dingtalk_webhook"]),
            "telegram_configured": bool(config["telegram_bot_token"]),
            "quiet_hours": f"{config['quiet_hours_start']}:00-{config['quiet_hours_end']}:00",
        },
        "queue_size": sum(len(msgs) for msgs in aggregated_cache.values()),
        "timestamp": datetime.now().isoformat(),
    })


@app.route('/test', methods=['POST'])
def test_notification():
    """测试通知"""
    success = dispatch_message("## 🧪 测试通知\n\n通知中心运行正常！", "测试通知", "dingtalk")
    return jsonify({"success": success})


@app.route('/flush', methods=['POST'])
def flush():
    """立即发送所有聚合消息"""
    process_aggregated()
    return jsonify({"status": "flushed"})


def create_app():
    """创建 Flask 应用"""
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key and key not in os.environ:
                        os.environ[key] = value

    config["dingtalk_webhook"] = os.environ.get("DINGTALK_WEBHOOK", "")
    config["dingtalk_secret"] = os.environ.get("DINGTALK_SECRET", "")
    config["telegram_bot_token"] = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    config["telegram_chat_id"] = os.environ.get("TELEGRAM_CHAT_ID", "")

    worker = threading.Thread(target=background_worker, daemon=True)
    worker.start()

    return app


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    app.run(host='0.0.0.0', port=5050, debug=False)
