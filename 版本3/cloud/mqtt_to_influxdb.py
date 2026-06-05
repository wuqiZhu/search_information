#!/usr/bin/env python3
"""
IoT智能环境监控系统 - 云端数据处理脚本
功能：MQTT数据采集、InfluxDB存储、数据聚合、异常检测、多渠道通知、数据清理
"""

import os
import sys
import json
import time
import signal
import logging
import threading
import base64
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Any

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, WriteOptions

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ===== 环境变量配置 =====
INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "your_org")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "your_bucket")

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")
MQTT_TOPICS = ["device/response", "device/telemetry", "device/alert", "device/heartbeat", "device/image_upload"]

# 通知渠道配置
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "")
WECHAT_WEBHOOK = os.environ.get("WECHAT_WEBHOOK", "")
ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")

# 数据保留配置
DATA_RETENTION_DAYS = int(os.environ.get("DATA_RETENTION_DAYS", "30"))
DATA_CLEANUP_INTERVAL = int(os.environ.get("DATA_CLEANUP_INTERVAL", "3600"))

# 聚合统计配置
AGGREGATION_INTERVAL = int(os.environ.get("AGGREGATION_INTERVAL", "300"))

# ===== 告警级别定义 =====
ALERT_LEVELS = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

# ===== 异常检测规则 =====
ALERT_RULES = [
    {
        "name": "high_temperature",
        "field": "temperature",
        "condition": "gt",
        "threshold": 35,
        "level": "HIGH",
        "message": "温度过高: {value}°C (阈值: {threshold}°C)"
    },
    {
        "name": "low_temperature",
        "field": "temperature",
        "condition": "lt",
        "threshold": 5,
        "level": "MEDIUM",
        "message": "温度过低: {value}°C (阈值: {threshold}°C)"
    },
    {
        "name": "high_humidity",
        "field": "humidity",
        "condition": "gt",
        "threshold": 90,
        "level": "MEDIUM",
        "message": "湿度过高: {value}% (阈值: {threshold}%)"
    },
    {
        "name": "low_humidity",
        "field": "humidity",
        "condition": "lt",
        "threshold": 20,
        "level": "MEDIUM",
        "message": "湿度过低: {value}% (阈值: {threshold}%)"
    },
    {
        "name": "smoke_detected",
        "field": "smoke_digital",
        "condition": "eq",
        "threshold": 0,
        "level": "CRITICAL",
        "message": "检测到烟雾!"
    },
    {
        "name": "high_cpu",
        "field": "cpu_usage",
        "condition": "gt",
        "threshold": 90,
        "level": "HIGH",
        "message": "CPU使用率过高: {value}% (阈值: {threshold}%)"
    },
    {
        "name": "high_memory",
        "field": "mem_usage",
        "condition": "gt",
        "threshold": 85,
        "level": "HIGH",
        "message": "内存使用率过高: {value}% (阈值: {threshold}%)"
    }
]

# ===== 告警冷却时间（秒） =====
ALERT_COOLDOWN = {
    "CRITICAL": 60,
    "HIGH": 300,
    "MEDIUM": 600,
    "LOW": 1800
}

# ===== 全局状态 =====
last_alert_time: Dict[str, float] = {}
sensor_buffer: Dict[str, List[float]] = defaultdict(list)
buffer_lock = threading.Lock()
running = True


def signal_handler(signum, frame):
    """信号处理"""
    global running
    logger.info(f"Received signal {signum}, shutting down...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ===== InfluxDB 客户端初始化 =====
if not INFLUXDB_TOKEN:
    logger.error("INFLUXDB_TOKEN 环境变量未设置")
    sys.exit(1)
if not MQTT_PASS:
    logger.error("MQTT_PASS 环境变量未设置")
    sys.exit(1)

influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)

write_options = WriteOptions(
    batch_size=10,
    flush_interval=5000,
    max_retries=3,
    retry_interval=1000,
    max_retry_delay=30000,
    exponential_base=2
)
write_api = influx_client.write_api(write_options=write_options)


def verify_influxdb_connection():
    """验证InfluxDB连接"""
    try:
        health = influx_client.health()
        if health.status == "pass":
            logger.info(f"InfluxDB连接成功: {health.message}")
            return True
        else:
            logger.error(f"InfluxDB健康检查失败: {health.status}")
            return False
    except Exception as e:
        logger.error(f"InfluxDB连接失败: {e}")
        return False


if not verify_influxdb_connection():
    logger.error("无法连接InfluxDB，退出...")
    sys.exit(1)


# ===== 通知渠道 =====
def send_dingtalk(title: str, content: str):
    """发送钉钉通知"""
    if not DINGTALK_WEBHOOK:
        return
    try:
        import requests
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"## 【通知】{title}\n\n{content}\n\n---\n*IoT 环境监控系统*"
            }
        }
        resp = requests.post(DINGTALK_WEBHOOK, json=payload, timeout=10)
        result = resp.json()
        if resp.status_code == 200 and result.get("errcode") == 0:
            logger.info(f"钉钉通知发送成功: {title}")
        else:
            logger.error(f"钉钉通知发送失败: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"钉钉通知异常: {e}")


def send_wechat(title: str, content: str):
    """发送企业微信通知"""
    if not WECHAT_WEBHOOK:
        return
    try:
        import requests
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"### {title}\n\n{content}"
            }
        }
        resp = requests.post(WECHAT_WEBHOOK, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"企业微信通知发送成功: {title}")
        else:
            logger.error(f"企业微信通知发送失败: {resp.status_code}")
    except Exception as e:
        logger.error(f"企业微信通知异常: {e}")


def send_generic_webhook(title: str, content: str):
    """发送通用Webhook通知"""
    if not ALERT_WEBHOOK_URL:
        return
    try:
        import requests
        payload = {"title": title, "content": content, "timestamp": int(time.time())}
        requests.post(ALERT_WEBHOOK_URL, json=payload, timeout=10)
        logger.info(f"Webhook通知发送成功: {title}")
    except Exception as e:
        logger.error(f"Webhook通知异常: {e}")


def send_notification(level: str, title: str, content: str):
    """发送通知到所有配置的渠道"""
    logger.info(f"[通知] [{level}] {title}: {content}")
    if level in ["CRITICAL", "HIGH"]:
        send_dingtalk(title, content)
        send_wechat(title, content)
        send_generic_webhook(title, content)
    elif level == "MEDIUM":
        send_dingtalk(title, content)
        send_wechat(title, content)


# ===== 异常检测引擎 =====
def check_alert_rules(field: str, value: float):
    """检查异常检测规则"""
    for rule in ALERT_RULES:
        if rule["field"] != field:
            continue

        triggered = False
        if rule["condition"] == "gt" and value > rule["threshold"]:
            triggered = True
        elif rule["condition"] == "lt" and value < rule["threshold"]:
            triggered = True
        elif rule["condition"] == "eq" and value == rule["threshold"]:
            triggered = True

        if triggered:
            alert_key = f"{rule['name']}_{field}"
            now = time.time()
            cooldown = ALERT_COOLDOWN.get(rule["level"], 300)

            if alert_key in last_alert_time and now - last_alert_time[alert_key] < cooldown:
                continue

            last_alert_time[alert_key] = now
            message = rule["message"].format(value=value, threshold=rule["threshold"])
            send_notification(rule["level"], f"告警: {rule['name']}", message)

            # 记录告警到InfluxDB
            point = Point("alert_events") \
                .tag("device", "imx6ull") \
                .tag("rule", rule["name"]) \
                .tag("level", rule["level"]) \
                .field("field", field) \
                .field("value", value) \
                .field("threshold", rule["threshold"]) \
                .field("message", message)
            try:
                write_api.write(bucket=INFLUXDB_BUCKET, record=point)
            except Exception as e:
                logger.error(f"写入告警事件失败: {e}")


# ===== 数据聚合统计 =====
def update_aggregation_buffer(field: str, value: float):
    """更新聚合缓冲区"""
    with buffer_lock:
        sensor_buffer[field].append(value)


def flush_aggregation():
    """刷新聚合数据到InfluxDB"""
    with buffer_lock:
        if not sensor_buffer:
            return

        now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        for field, values in sensor_buffer.items():
            if not values:
                continue

            avg_val = sum(values) / len(values)
            min_val = min(values)
            max_val = max(values)
            count = len(values)

            point = Point("sensor_aggregated") \
                .tag("device", "imx6ull") \
                .tag("field", field) \
                .tag("window", f"{AGGREGATION_INTERVAL}s") \
                .field("mean", round(avg_val, 2)) \
                .field("min", round(min_val, 2)) \
                .field("max", round(max_val, 2)) \
                .field("count", count)
            try:
                write_api.write(bucket=INFLUXDB_BUCKET, record=point)
            except Exception as e:
                logger.error(f"写入聚合数据失败: {e}")

        sensor_buffer.clear()
        logger.info(f"聚合数据已刷新")


def aggregation_thread():
    """聚合统计定时线程"""
    while running:
        time.sleep(AGGREGATION_INTERVAL)
        if running:
            flush_aggregation()


# ===== 数据保留策略 =====
def cleanup_old_data():
    """清理过期数据"""
    try:
        query_api = influx_client.query_api()
        retention = f"-{DATA_RETENTION_DAYS}d"

        buckets_to_clean = ["sensor_data", "device_alerts", "device_heartbeat", "alert_events"]

        for bucket in buckets_to_clean:
            try:
                query = f'''
                from(bucket: "{INFLUXDB_BUCKET}")
                    |> range(start: {retention})
                    |> filter(fn: (r) => r._measurement == "{bucket}")
                    |> drop()
                '''
                query_api.query(query, org=INFLUXDB_ORG)
                logger.info(f"已清理 {bucket} 中超过 {DATA_RETENTION_DAYS} 天的数据")
            except Exception as e:
                logger.debug(f"清理 {bucket} 数据时出错 (可能无数据): {e}")

    except Exception as e:
        logger.error(f"数据清理失败: {e}")


def cleanup_thread():
    """数据清理定时线程"""
    while running:
        time.sleep(DATA_CLEANUP_INTERVAL)
        if running:
            cleanup_old_data()


# ===== MQTT 消息处理 =====
def handle_alert(data: dict):
    """处理告警消息"""
    alert_type = data.get("alert_type", "unknown")
    level = data.get("level", "LOW").upper()
    message = data.get("message", "No message")

    if level in ["CRITICAL", "HIGH"]:
        logger.critical(f"ALERT [{level}] {alert_type}: {message}")
    elif level == "MEDIUM":
        logger.warning(f"ALERT [{level}] {alert_type}: {message}")
    else:
        logger.info(f"ALERT [{level}] {alert_type}: {message}")

    send_notification(level, f"设备告警: {alert_type}", message)


def handle_telemetry(data: dict):
    """处理遥测数据"""
    d = data.get("data", {})
    if not d:
        return

    point = Point("sensor_data").tag("device", "imx6ull")

    fields = {
        "pir": ("pir", int),
        "light": ("light", int),
        "humi": ("humidity", int),
        "temp": ("temperature", int),
        "relay": ("relay", int),
        "relay2": ("relay2", int),
        "smoke_digital": ("smoke_digital", int)
    }

    for src_key, (dst_key, converter) in fields.items():
        if src_key in d:
            try:
                val = converter(d[src_key])
                point.field(dst_key, val)
                update_aggregation_buffer(dst_key, val)
                check_alert_rules(dst_key, val)
            except (ValueError, TypeError):
                pass

    try:
        write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        logger.info(f"遥测数据已写入")
    except Exception as e:
        logger.error(f"写入遥测数据失败: {e}")


def handle_heartbeat(data: dict):
    """处理心跳消息"""
    point = Point("device_heartbeat").tag("device", "imx6ull")

    hb_fields = {
        "cpu_usage": ("cpu_usage", float),
        "mem_usage": ("mem_usage", float),
        "load_avg": ("load_avg", float),
        "uptime": ("uptime", int)
    }

    for src_key, (dst_key, converter) in hb_fields.items():
        if src_key in data:
            try:
                val = converter(data[src_key])
                point.field(dst_key, val)
                if dst_key in ["cpu_usage", "mem_usage"]:
                    check_alert_rules(dst_key, val)
            except (ValueError, TypeError):
                pass

    try:
        write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        logger.info("心跳数据已写入")
    except Exception as e:
        logger.error(f"写入心跳数据失败: {e}")


def handle_image_upload(data: dict):
    """处理图片上传"""
    event = data.get("event", "unknown")
    image_data = data.get("image_data", "")
    image_size = data.get("image_size", 0)
    timestamp = data.get("timestamp", int(time.time()))

    if image_data:
        try:
            img_bytes = base64.b64decode(image_data)
            os.makedirs("images", exist_ok=True)
            filename = f"images/{event}_{timestamp}.jpg"
            with open(filename, "wb") as f:
                f.write(img_bytes)
            logger.info(f"图片已保存: {filename} ({len(img_bytes)} bytes)")
        except Exception as e:
            logger.error(f"保存图片失败: {e}")

    point = Point("camera_images").tag("device", "imx6ull") \
        .field("event", event) \
        .field("image_size", image_size) \
        .field("timestamp", timestamp)
    try:
        write_api.write(bucket=INFLUXDB_BUCKET, record=point)
    except Exception as e:
        logger.error(f"写入图片事件失败: {e}")

    if event == "smoke_alert":
        handle_alert({
            "alert_type": "smoke_with_image",
            "level": "CRITICAL",
            "message": f"烟雾报警并拍照 ({image_size} bytes)"
        })


def on_connect(client, userdata, flags, rc):
    """MQTT连接回调"""
    if rc == 0:
        logger.info("已连接MQTT服务器")
        for topic in MQTT_TOPICS:
            client.subscribe(topic, qos=1)
            logger.info(f"已订阅: {topic}")
    else:
        logger.error(f"MQTT连接失败: rc={rc}")


def on_disconnect(client, userdata, rc):
    """MQTT断开回调"""
    if rc != 0:
        logger.warning(f"MQTT意外断开 (rc={rc})，将自动重连")


def on_message(client, userdata, msg):
    """MQTT消息回调"""
    try:
        data = json.loads(msg.payload.decode())
        topic = msg.topic
        method = data.get("method", "unknown")

        if topic == "device/alert":
            point = Point("device_alerts").tag("device", "imx6ull")
            for key in ["alert_type", "message", "level"]:
                if key in data:
                    point.field(key, str(data[key]))
            try:
                write_api.write(bucket=INFLUXDB_BUCKET, record=point)
            except Exception as e:
                logger.error(f"写入告警失败: {e}")
            handle_alert(data)
            return

        if topic == "device/heartbeat":
            handle_heartbeat(data)
            return

        if method == "image_upload":
            handle_image_upload(data)
            return

        if method == "telemetry" and "data" in data:
            handle_telemetry(data)
            return

        # 处理旧格式响应
        if data.get("success") != 1:
            return

        point = Point("sensor_data").tag("device", "imx6ull")
        if method == "pir_read" and "data" in data and "pir" in data["data"]:
            point.field("pir", int(data["data"]["pir"]))
        elif method == "light_read" and "data" in data and "light" in data["data"]:
            light_val = data["data"]["light"]
            if isinstance(light_val, list):
                light_val = light_val[0] if light_val else 0
            point.field("light", int(light_val))
        elif method == "dht11_read" and "data" in data:
            humi = data["data"].get("humi")
            temp = data["data"].get("temp")
            if humi is not None:
                point.field("humidity", int(humi))
            if temp is not None:
                point.field("temperature", int(temp))
        elif method == "smoke_digital_read" and "data" in data and "smoke_digital" in data["data"]:
            point.field("smoke_digital", int(data["data"]["smoke_digital"]))
        else:
            return

        try:
            write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        except Exception as e:
            logger.error(f"写入响应失败: {e}")

    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {e}")
    except Exception as e:
        logger.exception(f"处理消息异常: {e}")


# ===== 主程序 =====
def cleanup():
    """清理资源"""
    global running
    running = False
    try:
        flush_aggregation()
        write_api.close()
        influx_client.close()
        logger.info("InfluxDB连接已关闭")
    except Exception as e:
        logger.error(f"清理资源时出错: {e}")


import atexit
atexit.register(cleanup)

# 启动后台线程
agg_thread = threading.Thread(target=aggregation_thread, daemon=True)
agg_thread.start()
logger.info(f"聚合统计线程已启动 (间隔: {AGGREGATION_INTERVAL}秒)")

clean_thread = threading.Thread(target=cleanup_thread, daemon=True)
clean_thread.start()
logger.info(f"数据清理线程已启动 (间隔: {DATA_CLEANUP_INTERVAL}秒)")

# 启动MQTT客户端
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.reconnect_delay_set(min_delay=1, max_delay=60)

logger.info("正在连接MQTT服务器...")
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_forever()
