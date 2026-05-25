#!/usr/bin/env python3
"""
通知中心客户端库
其他项目可以通过此库发送信号到通知中心
支持两种模式：
1. API 模式：通过 HTTP API 发送信号
2. 直接模式：直接使用通知中心模块（当 API 服务器不可用时）
"""
import os
import sys
import requests
import json
import logging

logger = logging.getLogger(__name__)

class NotificationClient:
    """通知中心客户端"""
    
    def __init__(self, server_url='http://localhost:8080'):
        self.server_url = server_url.rstrip('/')
        self.timeout = 10
        self._direct_mode = False
        self._notification_center = None
        
        # 尝试导入通知中心模块（直接模式）
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from notification_center import NotificationCenter
            self._notification_center = NotificationCenter()
            self._direct_mode = True
            logger.info("Using direct mode (notification center module)")
        except ImportError:
            logger.info("Using API mode (notification center server)")
    
    def add_signal(self, signal, source='unknown'):
        """
        添加信号到通知中心
        
        Args:
            signal: 信号数据，包含以下字段：
                - title: 标题
                - url: 链接
                - content: 内容
                - source: 来源
                - keywords: 关键词列表
                - relevance_score: 相关性分数
            source: 信号来源（trendradar/find_job）
        
        Returns:
            bool: 是否成功添加
        """
        # 直接模式：使用通知中心模块
        if self._direct_mode and self._notification_center:
            try:
                return self._notification_center.add_signal(signal, source)
            except Exception as e:
                logger.error(f"Failed to add signal in direct mode: {e}")
                return False
        
        # API 模式：通过 HTTP API 发送信号
        try:
            response = requests.post(
                f"{self.server_url}/signal",
                json={
                    'signal': signal,
                    'source': source
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                status = result.get('status')
                message = result.get('message', '')
                
                if status == 'added':
                    logger.info(f"Signal added: {signal.get('title', '')[:50]}")
                    return True
                elif status == 'duplicate':
                    logger.debug(f"Duplicate signal: {signal.get('title', '')[:50]}")
                    return False
                else:
                    logger.warning(f"Unexpected status: {status} - {message}")
                    return False
            else:
                logger.error(f"Failed to add signal: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to notification center: {e}")
            return False
    
    def update_preference(self, signal, action):
        """
        更新用户偏好
        
        Args:
            signal: 信号数据
            action: 用户操作（like/dislike）
        
        Returns:
            bool: 是否成功更新
        """
        # 直接模式：使用通知中心模块
        if self._direct_mode and self._notification_center:
            try:
                self._notification_center.update_preferences(signal, action)
                logger.info(f"Preference updated (direct mode): {action} - {signal.get('title', '')[:50]}")
                return True
            except Exception as e:
                logger.error(f"Failed to update preference in direct mode: {e}")
                return False
        
        # API 模式：通过 HTTP API 更新偏好
        try:
            response = requests.post(
                f"{self.server_url}/preference",
                json={
                    'signal': signal,
                    'action': action
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Preference updated: {action} - {signal.get('title', '')[:50]}")
                return True
            else:
                logger.error(f"Failed to update preference: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to notification center: {e}")
            return False
    
    def process_queue(self):
        """
        处理通知队列
        
        Returns:
            bool: 是否成功处理
        """
        # 直接模式：使用通知中心模块
        if self._direct_mode and self._notification_center:
            try:
                self._notification_center.process_queue()
                logger.info("Queue processed (direct mode)")
                return True
            except Exception as e:
                logger.error(f"Failed to process queue in direct mode: {e}")
                return False
        
        # API 模式：通过 HTTP API 处理队列
        try:
            response = requests.post(
                f"{self.server_url}/process",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info("Queue processed")
                return True
            else:
                logger.error(f"Failed to process queue: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to notification center: {e}")
            return False
    
    def get_stats(self):
        """
        获取统计信息
        
        Returns:
            dict: 统计信息
        """
        # 直接模式：使用通知中心模块
        if self._direct_mode and self._notification_center:
            try:
                return self._notification_center.get_stats()
            except Exception as e:
                logger.error(f"Failed to get stats in direct mode: {e}")
                return None
        
        # API 模式：通过 HTTP API 获取统计信息
        try:
            response = requests.get(
                f"{self.server_url}/stats",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get stats: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to notification center: {e}")
            return None
    
    def health_check(self):
        """
        健康检查
        
        Returns:
            bool: 服务器是否正常
        """
        try:
            response = requests.get(
                f"{self.server_url}/health",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False

# 全局客户端实例
_client = None

def get_client(server_url='http://localhost:8080'):
    """获取客户端单例"""
    global _client
    if _client is None:
        _client = NotificationClient(server_url)
    return _client

def add_signal(signal, source='unknown'):
    """添加信号"""
    client = get_client()
    return client.add_signal(signal, source)

def update_preference(signal, action):
    """更新偏好"""
    client = get_client()
    return client.update_preference(signal, action)

def process_queue():
    """处理队列"""
    client = get_client()
    return client.process_queue()

def get_stats():
    """获取统计"""
    client = get_client()
    return client.get_stats()

def health_check():
    """健康检查"""
    client = get_client()
    return client.health_check()
