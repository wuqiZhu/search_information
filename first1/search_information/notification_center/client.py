"""统一通知中心客户端

其他项目通过此客户端发送通知到通知中心。

使用方式：
    from notification_center.client import NotificationClient

    client = NotificationClient("http://localhost:5050")
    client.send("华为裁员消息", priority="high", source="TrendRadar")
    client.send_urgent("紧急：Cookie 已过期", source="find_job")
    client.send_digest("今日摘要内容", source="analyse_information")
"""

import json
import urllib.request
import logging

logger = logging.getLogger(__name__)


class NotificationClient:
    """通知中心客户端"""

    def __init__(self, server_url: str = "http://localhost:5050", timeout: int = 10):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout

    def send(self, text: str, title: str = "通知", priority: str = "high",
             source: str = "", channel: str = "dingtalk", tags: list = None) -> dict:
        """发送通知"""
        payload = {
            "text": text,
            "title": title,
            "priority": priority,
            "source": source,
            "channel": channel,
            "tags": tags or [],
        }
        return self._post("/notify", payload)

    def send_urgent(self, text: str, title: str = "紧急通知", source: str = "", channel: str = "dingtalk") -> dict:
        """发送紧急通知（立即推送）"""
        return self.send(text, title, priority="urgent", source=source, channel=channel)

    def send_high(self, text: str, title: str = "通知", source: str = "", channel: str = "dingtalk") -> dict:
        """发送高优先级通知（实时推送）"""
        return self.send(text, title, priority="high", source=source, channel=channel)

    def send_medium(self, text: str, title: str = "通知", source: str = "", channel: str = "dingtalk") -> dict:
        """发送中优先级通知（聚合推送）"""
        return self.send(text, title, priority="medium", source=source, channel=channel)

    def send_digest(self, text: str, title: str = "每日摘要", source: str = "", channel: str = "dingtalk") -> dict:
        """发送低优先级通知（每日汇总）"""
        return self.send(text, title, priority="low", source=source, channel=channel)

    def health(self) -> dict:
        """检查通知中心健康状态"""
        return self._get("/health")

    def test(self) -> dict:
        """发送测试通知"""
        return self._post("/test", {})

    def flush(self) -> dict:
        """立即发送所有聚合消息"""
        return self._post("/flush", {})

    def _post(self, path: str, data: dict) -> dict:
        """发送 POST 请求"""
        try:
            url = f"{self.server_url}{path}"
            payload = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"通知中心请求失败: {e}")
            return {"error": str(e)}

    def _get(self, path: str) -> dict:
        """发送 GET 请求"""
        try:
            url = f"{self.server_url}{path}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"通知中心请求失败: {e}")
            return {"error": str(e)}


# 便捷函数
_default_client = None


def get_client(server_url: str = None) -> NotificationClient:
    """获取默认客户端实例"""
    global _default_client
    if _default_client is None:
        url = server_url or "http://localhost:5050"
        _default_client = NotificationClient(url)
    return _default_client


def notify(text: str, priority: str = "high", source: str = "", title: str = "通知"):
    """便捷通知函数"""
    client = get_client()
    return client.send(text, title=title, priority=priority, source=source)
