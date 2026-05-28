# -*- coding: utf-8 -*-
"""
健康监控与告警模块

功能：
1. 服务健康检查 - 定期检查各服务状态
2. 容器状态监控 - Docker容器运行状态
3. 异常告警 - 服务异常时发送告警
4. 每日运行报告 - 汇总系统运行情况
"""

import os
import json
import time
import urllib.request
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class HealthMonitor:
    """健康监控器"""

    def __init__(self, config: Dict = None):
        self.config = config or {}

        # 监控的服务
        # 在 Docker 网络中，使用容器名称作为主机名
        self.services = self.config.get('services', {
            'trendradar': {
                'type': 'process',  # 无HTTP端口，检查进程
                'check_interval': 300,
                'alert_threshold': 3,
            },
            'analyser': {
                'type': 'process',  # 无HTTP端口，检查进程
                'check_interval': 600,
                'alert_threshold': 3,
            },
            'invest-backend': {
                'type': 'http',
                'url': 'http://invest-backend:5000/health',
                'check_interval': 300,
                'alert_threshold': 3,
            },
            'invest-frontend': {
                'type': 'http',
                'url': 'http://invest-frontend:3000',
                'check_interval': 300,
                'alert_threshold': 3,
            },
            'notification-center': {
                'type': 'http',
                'url': 'http://localhost:5050/health',  # 自己检查自己用 localhost
                'check_interval': 300,
                'alert_threshold': 3,
            },
            'dashboard': {
                'type': 'http',
                'url': 'http://dashboard:5060',
                'check_interval': 300,
                'alert_threshold': 3,
            },
        })

        # 服务状态
        self.service_status: Dict[str, Dict] = {}

        # 告警历史
        self.alert_history: Dict[str, List[Dict]] = {}

        # 通知回调
        self.notify_callback = None

        # 运行统计
        self.stats = {
            'start_time': datetime.now().isoformat(),
            'checks_performed': 0,
            'alerts_sent': 0,
            'last_check_time': None,
        }

        # 停止标志
        self._stop_event = threading.Event()

    def set_notify_callback(self, callback):
        """设置通知回调函数"""
        self.notify_callback = callback

    def check_container_status(self, container_name: str) -> Tuple[bool, str]:
        """
        检查Docker容器状态

        Returns:
            (is_running, status_message)
        """
        try:
            import subprocess
            result = subprocess.run(
                ['docker', 'inspect', '--format', '{{.State.Status}}', container_name],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                status = result.stdout.strip()
                if status == 'running':
                    return True, f"运行中"
                else:
                    return False, f"状态异常: {status}"
            else:
                return False, f"容器不存在或检查失败"

        except Exception as e:
            return False, f"检查失败: {str(e)}"

    def check_http_health(self, url: str, timeout: int = 10) -> Tuple[bool, str]:
        """
        检查HTTP服务健康状态

        Returns:
            (is_healthy, status_message)
        """
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True, f"HTTP {resp.status}"
                else:
                    return False, f"HTTP {resp.status}"

        except urllib.error.URLError as e:
            return False, f"连接失败: {str(e)}"
        except Exception as e:
            return False, f"检查失败: {str(e)}"

    def check_process_status(self, service_name: str) -> Tuple[bool, str]:
        """
        检查进程状态（通过检查容器内的进程）

        Returns:
            (is_running, status_message)
        """
        try:
            import subprocess
            # 检查容器是否在运行（通过检查进程）
            result = subprocess.run(
                ['pgrep', '-f', service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return True, "进程运行中"
            else:
                return False, "进程未找到"
        except Exception as e:
            return False, f"检查失败: {str(e)}"

    def check_service(self, service_name: str) -> Tuple[bool, str]:
        """
        检查单个服务状态

        Returns:
            (is_healthy, status_message)
        """
        service_config = self.services.get(service_name, {})
        check_type = service_config.get('type', 'container')

        if check_type == 'container':
            return self.check_container_status(service_name)
        elif check_type == 'process':
            # 对于 process 类型，尝试通过 docker socket 检查
            return self.check_container_via_api(service_name)
        elif check_type == 'http':
            url = service_config.get('url', '')
            if url:
                return self.check_http_health(url)
            return False, "未配置URL"
        else:
            return False, f"未知检查类型: {check_type}"

    def check_container_via_api(self, container_name: str) -> Tuple[bool, str]:
        """
        通过 Docker API 检查容器状态

        Returns:
            (is_running, status_message)
        """
        try:
            # 尝试通过 docker.sock 检查
            import socket
            import json

            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect('/var/run/docker.sock')

            request = f"GET /containers/{container_name}/json HTTP/1.1\r\nHost: localhost\r\n\r\n"
            sock.send(request.encode())

            response = b""
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                response += data

            sock.close()

            if b"200 OK" in response:
                # 解析响应获取状态
                body = response.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in response else b""
                if body:
                    container_info = json.loads(body)
                    state = container_info.get('State', {})
                    if state.get('Running'):
                        return True, "运行中"
                    else:
                        return False, f"已停止: {state.get('Status', 'unknown')}"
                return True, "运行中"
            else:
                return False, "容器不存在"

        except FileNotFoundError:
            # Docker socket 不存在，尝试 HTTP 方式
            try:
                req = urllib.request.Request(
                    f"http://localhost:5050/health",
                    method='GET'
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return True, "服务可达"
            except:
                pass
            return False, "无法检查容器状态"
        except Exception as e:
            return False, f"检查失败: {str(e)}"

    def check_all_services(self) -> Dict[str, Dict]:
        """
        检查所有服务状态

        Returns:
            {service_name: {healthy: bool, message: str, last_check: str}}
        """
        results = {}

        for service_name in self.services:
            is_healthy, message = self.check_service(service_name)

            # 更新状态
            if service_name not in self.service_status:
                self.service_status[service_name] = {
                    'healthy': is_healthy,
                    'message': message,
                    'consecutive_failures': 0 if is_healthy else 1,
                    'last_check': datetime.now().isoformat(),
                    'last_alert': None,
                }
            else:
                prev_status = self.service_status[service_name]
                if not is_healthy:
                    prev_status['consecutive_failures'] += 1
                else:
                    prev_status['consecutive_failures'] = 0

                prev_status['healthy'] = is_healthy
                prev_status['message'] = message
                prev_status['last_check'] = datetime.now().isoformat()

            results[service_name] = self.service_status[service_name]

            # 检查是否需要告警
            self._check_alert(service_name, is_healthy)

        self.stats['checks_performed'] += 1
        self.stats['last_check_time'] = datetime.now().isoformat()

        return results

    def _check_alert(self, service_name: str, is_healthy: bool):
        """检查是否需要发送告警"""
        status = self.service_status[service_name]
        service_config = self.services.get(service_name, {})
        alert_threshold = service_config.get('alert_threshold', 3)

        # 连续失败达到阈值
        if not is_healthy and status['consecutive_failures'] >= alert_threshold:
            # 检查是否已经告警过（1小时内不重复告警）
            last_alert = status.get('last_alert')
            if last_alert:
                last_alert_time = datetime.fromisoformat(last_alert)
                if datetime.now() - last_alert_time < timedelta(hours=1):
                    return

            # 发送告警
            self._send_alert(service_name, status)
            status['last_alert'] = datetime.now().isoformat()

        # 服务恢复通知
        elif is_healthy and status['consecutive_failures'] > 0:
            # 之前有失败，现在恢复了
            if status['consecutive_failures'] >= alert_threshold:
                self._send_recovery(service_name)
            status['consecutive_failures'] = 0

    def _send_alert(self, service_name: str, status: Dict):
        """发送告警通知"""
        if not self.notify_callback:
            logger.warning("未设置通知回调，无法发送告警")
            return

        message = {
            'text': f"""## ⚠️ 服务告警

**服务**: {service_name}
**状态**: {status['message']}
**连续失败**: {status['consecutive_failures']}次
**检查时间**: {status['last_check']}

请及时检查服务状态！""",
            'title': f"服务告警: {service_name}",
            'priority': 'urgent',
            'source': 'health_monitor',
            'tags': ['alert', 'urgent'],
        }

        self.notify_callback(message)
        self.stats['alerts_sent'] += 1

        logger.warning(f"服务告警: {service_name} - {status['message']}")

    def _send_recovery(self, service_name: str):
        """发送恢复通知"""
        if not self.notify_callback:
            return

        message = {
            'text': f"""## ✅ 服务恢复

**服务**: {service_name}
**状态**: 已恢复正常
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}""",
            'title': f"服务恢复: {service_name}",
            'priority': 'high',
            'source': 'health_monitor',
            'tags': ['recovery'],
        }

        self.notify_callback(message)
        logger.info(f"服务恢复: {service_name}")

    def generate_daily_report(self) -> str:
        """生成每日运行报告"""
        now = datetime.now()

        lines = [
            f"## 📊 系统每日报告",
            f"**日期**: {now.strftime('%Y-%m-%d')}",
            f"**生成时间**: {now.strftime('%H:%M:%S')}",
            "",
            "### 服务状态",
            "",
        ]

        # 检查所有服务
        results = self.check_all_services()

        healthy_count = sum(1 for s in results.values() if s['healthy'])
        total_count = len(results)

        lines.append(f"**总服务数**: {total_count}")
        lines.append(f"**正常运行**: {healthy_count}")
        lines.append(f"**异常服务**: {total_count - healthy_count}")
        lines.append("")

        for service_name, status in results.items():
            emoji = "✅" if status['healthy'] else "❌"
            lines.append(f"- {emoji} **{service_name}**: {status['message']}")

        lines.append("")
        lines.append("### 运行统计")
        lines.append("")
        lines.append(f"- 监控启动时间: {self.stats['start_time']}")
        lines.append(f"- 检查次数: {self.stats['checks_performed']}")
        lines.append(f"- 告警次数: {self.stats['alerts_sent']}")

        return "\n".join(lines)

    def _monitor_loop(self):
        """监控主循环"""
        logger.info("健康监控已启动")

        while not self._stop_event.is_set():
            try:
                # 检查所有服务
                self.check_all_services()

                # 检查是否需要发送每日报告（每天9点）
                now = datetime.now()
                if now.hour == 9 and now.minute < 5:
                    report = self.generate_daily_report()
                    if self.notify_callback:
                        self.notify_callback({
                            'text': report,
                            'title': '每日系统报告',
                            'priority': 'medium',
                            'source': 'health_monitor',
                            'tags': ['daily_report'],
                        })

            except Exception as e:
                logger.error(f"监控循环异常: {e}")

            # 等待下一次检查（默认5分钟）
            self._stop_event.wait(300)

    def start(self):
        """启动监控"""
        self._stop_event.clear()
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
        return thread

    def stop(self):
        """停止监控"""
        self._stop_event.set()

    def get_status(self) -> Dict:
        """获取监控状态"""
        return {
            'stats': self.stats,
            'services': self.service_status,
            'is_running': not self._stop_event.is_set(),
        }


# 全局实例
_monitor_instance = None


def get_health_monitor(config: Dict = None) -> HealthMonitor:
    """获取全局健康监控器实例"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = HealthMonitor(config)
    return _monitor_instance
