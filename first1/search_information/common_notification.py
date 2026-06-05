# -*- coding: utf-8 -*-
"""
统一钉钉通知模块
所有模块共享使用，确保关键词"通知"正确添加
"""

import os
import requests
import hmac
import hashlib
import base64
import urllib.parse
import time


class DingTalkNotifier:
    """统一钉钉通知器"""
    
    def __init__(self, webhook_url=None, secret=None):
        """
        初始化钉钉通知器
        
        Args:
            webhook_url: 钉钉机器人webhook地址
            secret: 钉钉机器人加签密钥（可选）
        """
        self.webhook_url = webhook_url or os.environ.get('DINGTALK_WEBHOOK')
        self.secret = secret or os.environ.get('DINGTALK_SECRET')
    
    def send(self, content, title=None, msgtype='markdown'):
        """
        发送钉钉通知
        
        Args:
            content: 通知内容
            title: 消息标题（仅markdown类型使用）
            msgtype: 消息类型 (text/markdown)
            
        Returns:
            bool: 是否发送成功
        """
        if not self.webhook_url:
            print("未配置钉钉webhook，跳过通知")
            return False
        
        # 确保消息包含关键词"通知"（钉钉机器人安全设置要求）
        if "通知" not in content:
            content = f"**通知**\n\n{content}"
        
        # 构建webhook地址（如果有secret则加签）
        final_url = self.webhook_url
        if self.secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f'{timestamp}\n{self.secret}'
            hmac_code = hmac.new(
                self.secret.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                digestmod=hashlib.sha256
            ).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            final_url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
        
        # 构建请求数据
        if msgtype == 'markdown':
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title or "TrendRadar 通知",
                    "text": content,
                },
            }
        else:
            payload = {
                "msgtype": "text",
                "text": {"content": content}
            }
        
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(
                final_url, 
                headers=headers, 
                json=payload, 
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    print("钉钉通知发送成功")
                    return True
                else:
                    print(f"钉钉通知失败: {result.get('errmsg')}")
                    return False
            else:
                print(f"钉钉通知请求失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"钉钉通知异常: {e}")
            return False


# 全局通知器实例
_notifier = None


def get_notifier():
    """获取全局钉钉通知器实例"""
    global _notifier
    if _notifier is None:
        _notifier = DingTalkNotifier()
    return _notifier


def send_dingtalk(content, title=None, msgtype='markdown'):
    """
    快速发送钉钉通知（便捷函数）
    
    Args:
        content: 通知内容
        title: 消息标题
        msgtype: 消息类型
        
    Returns:
        bool: 是否发送成功
    """
    notifier = get_notifier()
    return notifier.send(content, title, msgtype)
