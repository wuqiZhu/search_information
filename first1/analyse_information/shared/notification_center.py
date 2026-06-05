#!/usr/bin/env python3
"""
智能通知中心
统一管理所有通知，实现优先级排序、时间窗口合并、去重处理
"""
import os
import json
import time
import hashlib
import logging
import requests
from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading

logger = logging.getLogger(__name__)

class NotificationCenter:
    """智能通知中心"""
    
    def __init__(self, config_path=None):
        # 加载配置
        self.config = self._load_config(config_path)
        
        # 通知队列
        self.queue = []
        self.queue_lock = threading.Lock()
        
        # 已发送通知的哈希值（用于去重）
        self.sent_hashes = set()
        self.sent_hashes_order = deque(maxlen=10000)
        self.hash_lock = threading.Lock()
        
        # 用户偏好（从反馈中学习）
        self.preferences = {
            'liked': [],
            'disliked': []
        }
        
        # 时间窗口配置
        self.merge_window_minutes = 10
        self.last_merge_time = datetime.now() - timedelta(hours=1)
        
        # 钉钉配置
        self.dingtalk_webhook = self.config.get('dingtalk', {}).get('webhook', '')
        self.dingtalk_secret = self.config.get('dingtalk', {}).get('secret', '')
        
        # 加载历史数据
        self._load_history()
    
    def _load_config(self, config_path):
        """加载配置文件"""
        import yaml
        
        config = {}
        
        # 1. 加载通知中心配置
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'notification_config.yaml')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        
        # 2. 如果没有钉钉配置，尝试从 TrendRadar 读取
        if not config.get('dingtalk', {}).get('webhook'):
            # 路径：analyse_information/shared/ -> project/ -> search_information/TrendRadar/
            trendradar_config_path = os.path.join(
                os.path.dirname(__file__), '..', '..', 
                'search_information', 'TrendRadar', 'config.yaml'
            )
            
            if os.path.exists(trendradar_config_path):
                try:
                    with open(trendradar_config_path, 'r', encoding='utf-8') as f:
                        trendradar_config = yaml.safe_load(f) or {}
                    
                    dingtalk_config = trendradar_config.get('notifications', {}).get('dingtalk', {})
                    if dingtalk_config:
                        # 展开环境变量
                        webhook = dingtalk_config.get('webhook', '')
                        secret = dingtalk_config.get('secret', '')
                        
                        # 处理 ${VAR} 格式的环境变量
                        if webhook.startswith('${') and webhook.endswith('}'):
                            env_var = webhook[2:-1]
                            webhook = os.environ.get(env_var, '')
                        
                        if secret.startswith('${') and secret.endswith('}'):
                            env_var = secret[2:-1]
                            secret = os.environ.get(env_var, '')
                        
                        dingtalk_config['webhook'] = webhook
                        dingtalk_config['secret'] = secret
                        
                        config['dingtalk'] = dingtalk_config
                        logger.info("Loaded DingTalk config from TrendRadar")
                except Exception as e:
                    logger.error(f"Failed to load TrendRadar config: {e}")
        
        # 3. 支持环境变量
        dingtalk_webhook = os.environ.get('DINGTALK_WEBHOOK')
        dingtalk_secret = os.environ.get('DINGTALK_SECRET')
        
        if dingtalk_webhook:
            if 'dingtalk' not in config:
                config['dingtalk'] = {}
            config['dingtalk']['webhook'] = dingtalk_webhook
        
        if dingtalk_secret:
            if 'dingtalk' not in config:
                config['dingtalk'] = {}
            config['dingtalk']['secret'] = dingtalk_secret
        
        return config
    
    def _load_history(self):
        """加载历史数据"""
        history_path = os.path.join(os.path.dirname(__file__), 'data', 'notification_history.json')
        
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.sent_hashes = set(data.get('sent_hashes', []))
                    self.preferences = data.get('preferences', self.preferences)
                    logger.info(f"Loaded {len(self.sent_hashes)} sent hashes")
            except Exception as e:
                logger.error(f"Failed to load history: {e}")
    
    def _save_history(self):
        """保存历史数据"""
        history_path = os.path.join(os.path.dirname(__file__), 'data', 'notification_history.json')
        
        try:
            os.makedirs(os.path.dirname(history_path), exist_ok=True)
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'sent_hashes': list(self.sent_hashes),
                    'preferences': self.preferences
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    def _generate_hash(self, signal):
        """生成信号的哈希值"""
        content = f"{signal.get('source', '')}{signal.get('title', '')}{signal.get('url', '')}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _is_duplicate(self, signal):
        """检查是否重复信号"""
        signal_hash = self._generate_hash(signal)
        with self.hash_lock:
            return signal_hash in self.sent_hashes
    
    def _mark_sent(self, signal):
        """标记信号已发送"""
        signal_hash = self._generate_hash(signal)
        with self.hash_lock:
            self.sent_hashes.add(signal_hash)
            self.sent_hashes_order.append(signal_hash)
            # 当 deque 满时自动移除最早的元素，同步更新 set
            if len(self.sent_hashes_order) == self.sent_hashes_order.maxlen:
                # 重建 set（保留 deque 中的所有元素）
                self.sent_hashes = set(self.sent_hashes_order)
    
    def add_signal(self, signal, source='unknown'):
        """
        添加信号到队列
        
        Args:
            signal: 信号数据
            source: 信号来源（trendradar/find_job）
        """
        # 检查重复
        if self._is_duplicate(signal):
            logger.debug(f"Duplicate signal: {signal.get('title', '')[:50]}")
            return False
        
        # 添加来源信息
        signal['source_type'] = source
        signal['added_at'] = datetime.now().isoformat()
        
        # 计算优先级
        signal['priority'] = self._calculate_priority(signal)
        
        with self.queue_lock:
            self.queue.append(signal)
            logger.info(f"Added signal: {signal.get('title', '')[:50]} (Priority: {signal['priority']})")
        
        return True
    
    def _calculate_priority(self, signal):
        """计算信号优先级"""
        keywords = signal.get('keywords', [])
        relevance_score = signal.get('relevance_score', 0)
        
        # P0: 求职招聘、面经题库
        job_keywords = ['实习', '校招', '春招', '秋招', '提前批', '应届生']
        interview_keywords = ['面经', '面试', '笔试', '手撕代码', '面试题']
        
        has_job = any(kw in job_keywords for kw in keywords)
        has_interview = any(kw in interview_keywords for kw in keywords)
        
        if has_job or has_interview:
            return 'P0'
        
        # P1: 政策福利、行业动态
        policy_keywords = ['补贴', '优惠', '学生', 'GitHub Student', '学生包']
        industry_keywords = ['嵌入式', 'Linux内核', 'RISC-V', 'ARM', '驱动开发']
        
        has_policy = any(kw in policy_keywords for kw in keywords)
        has_industry = any(kw in industry_keywords for kw in keywords)
        
        if has_policy or has_industry:
            return 'P1'
        
        # P2: 长期杠杆
        return 'P2'
    
    def process_queue(self):
        """
        处理队列中的信号
        按优先级发送通知
        """
        with self.queue_lock:
            if not self.queue:
                return
            
            # 按优先级排序
            priority_order = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
            self.queue.sort(key=lambda x: priority_order.get(x.get('priority', 'P3'), 3))
            
            # 检查时间窗口
            current_time = datetime.now()
            time_since_last = (current_time - self.last_merge_time).total_seconds() / 60
            
            if time_since_last < self.merge_window_minutes:
                logger.debug(f"Within merge window ({time_since_last:.1f} < {self.merge_window_minutes} minutes)")
                return
            
            # 处理队列
            signals_to_send = []
            while self.queue:
                signal = self.queue.pop(0)
                
                # P0 立即发送
                if signal.get('priority') == 'P0':
                    signals_to_send.append(signal)
                # P1/P2 合并发送
                else:
                    signals_to_send.append(signal)
            
            # 发送通知
            if signals_to_send:
                self._send_batch_notification(signals_to_send)
                self.last_merge_time = current_time
    
    def _send_batch_notification(self, signals):
        """批量发送通知"""
        if not signals:
            return
        
        # 按来源分组
        grouped_signals = defaultdict(list)
        for signal in signals:
            source_type = signal.get('source_type', 'unknown')
            grouped_signals[source_type].append(signal)
        
        # 发送通知
        for source_type, source_signals in grouped_signals.items():
            if source_type == 'trendradar':
                self._send_trendradar_notification(source_signals)
            elif source_type == 'find_job':
                self._send_find_job_notification(source_signals)
            else:
                self._send_generic_notification(source_signals)
            
            # 标记已发送
            for signal in source_signals:
                self._mark_sent(signal)
    
    def _send_trendradar_notification(self, signals):
        """发送 TrendRadar 通知"""
        if not signals:
            return
        
        # 构建通知内容
        title = f"TrendRadar通知: 发现 {len(signals)} 条行业信息"
        
        # 构建内容
        content_lines = []
        for i, signal in enumerate(signals[:5], 1):  # 最多显示 5 条
            priority = signal.get('priority', 'P2')
            emoji = '🔥' if priority == 'P0' else '⭐' if priority == 'P1' else '📌'
            content_lines.append(f"{emoji} **{signal.get('title', '')[:50]}**")
            content_lines.append(f"   来源: {signal.get('source', '')} | 优先级: {priority}")
            content_lines.append("")
        
        if len(signals) > 5:
            content_lines.append(f"... 还有 {len(signals) - 5} 条信息")
        
        content = "\n".join(content_lines)
        
        # 发送钉钉通知
        self._send_dingtalk_notification(title, content, signals)
    
    def _send_find_job_notification(self, signals):
        """发送 find_job 通知"""
        if not signals:
            return
        
        # 构建通知内容
        title = f"find_job通知: 发现 {len(signals)} 条求职信息"
        
        # 构建内容
        content_lines = []
        for i, signal in enumerate(signals[:5], 1):  # 最多显示 5 条
            priority = signal.get('priority', 'P2')
            emoji = '🔥' if priority == 'P0' else '⭐' if priority == 'P1' else '📌'
            content_lines.append(f"{emoji} **{signal.get('title', '')[:50]}**")
            content_lines.append(f"   来源: {signal.get('source', '')} | 优先级: {priority}")
            content_lines.append("")
        
        if len(signals) > 5:
            content_lines.append(f"... 还有 {len(signals) - 5} 条信息")
        
        content = "\n".join(content_lines)
        
        # 发送钉钉通知
        self._send_dingtalk_notification(title, content, signals)
    
    def _send_generic_notification(self, signals):
        """发送通用通知"""
        if not signals:
            return
        
        # 构建通知内容
        title = f"通知: 发现 {len(signals)} 条新信息"
        
        # 构建内容
        content_lines = []
        for i, signal in enumerate(signals[:5], 1):  # 最多显示 5 条
            priority = signal.get('priority', 'P2')
            emoji = '🔥' if priority == 'P0' else '⭐' if priority == 'P1' else '📌'
            content_lines.append(f"{emoji} **{signal.get('title', '')[:50]}**")
            content_lines.append(f"   来源: {signal.get('source', '')} | 优先级: {priority}")
            content_lines.append("")
        
        if len(signals) > 5:
            content_lines.append(f"... 还有 {len(signals) - 5} 条信息")
        
        content = "\n".join(content_lines)
        
        # 发送钉钉通知
        self._send_dingtalk_notification(title, content, signals)
    
    def _send_dingtalk_notification(self, title, content, signals):
        """发送钉钉通知"""
        if not self.dingtalk_webhook:
            logger.warning("DingTalk webhook not configured")
            return False
        
        try:
            # 确保标题包含"通知"关键词（钉钉安全模式要求）
            if '通知' not in title:
                title = f"通知: {title}"
            
            # 构建 ActionCard 消息
            markdown_text = f"## {title}\n\n{content}\n\n"
            
            # 添加查看详情按钮
            if signals:
                first_signal = signals[0]
                url = first_signal.get('url', '')
                if url:
                    markdown_text += f"[查看详情]({url})\n\n"
            
            # 添加收藏/忽略按钮
            markdown_text += "---\n\n"
            markdown_text += "👍 收藏 | 👎 忽略"
            
            payload = {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title,
                    "text": markdown_text,
                    "btnOrientation": "0",
                    "singleTitle": "查看详情",
                    "singleURL": signals[0].get('url', '') if signals else ''
                }
            }
            
            # 构建 webhook URL（支持加签模式）
            webhook_url = self.dingtalk_webhook
            if self.dingtalk_secret:
                timestamp = str(round(time.time() * 1000))
                string_to_sign = f"{timestamp}\n{self.dingtalk_secret}"
                import hmac
                import hashlib
                import base64
                import urllib.parse
                
                hmac_code = hmac.new(
                    self.dingtalk_secret.encode('utf-8'),
                    string_to_sign.encode('utf-8'),
                    digestmod=hashlib.sha256
                ).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
                webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"
            
            # 发送请求
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    logger.info(f"DingTalk notification sent successfully: {title}")
                    return True
                else:
                    logger.error(f"DingTalk notification failed: {result}")
                    return False
            else:
                logger.error(f"DingTalk notification failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send DingTalk notification: {e}")
            return False
    
    def update_preferences(self, signal, action):
        """
        更新用户偏好
        
        Args:
            signal: 信号数据
            action: 用户操作（like/dislike）
        """
        signal_info = {
            'title': signal.get('title', ''),
            'category': signal.get('category', ''),
            'source': signal.get('source', '')
        }
        
        if action == 'like':
            self.preferences['liked'].append(signal_info)
            # 保留最近 100 个
            if len(self.preferences['liked']) > 100:
                self.preferences['liked'] = self.preferences['liked'][-100:]
        elif action == 'dislike':
            self.preferences['disliked'].append(signal_info)
            # 保留最近 100 个
            if len(self.preferences['disliked']) > 100:
                self.preferences['disliked'] = self.preferences['disliked'][-100:]
        
        # 保存偏好
        self._save_history()
        
        logger.info(f"Updated preferences: {action} - {signal.get('title', '')[:50]}")
    
    def get_stats(self):
        """获取统计信息"""
        with self.queue_lock:
            queue_size = len(self.queue)
        
        with self.hash_lock:
            sent_count = len(self.sent_hashes)
        
        return {
            'queue_size': queue_size,
            'sent_count': sent_count,
            'preferences': {
                'liked_count': len(self.preferences['liked']),
                'disliked_count': len(self.preferences['disliked'])
            }
        }

# 全局实例
_notification_center = None

def get_notification_center():
    """获取通知中心单例"""
    global _notification_center
    if _notification_center is None:
        _notification_center = NotificationCenter()
    return _notification_center

def add_signal(signal, source='unknown'):
    """添加信号到通知中心"""
    center = get_notification_center()
    return center.add_signal(signal, source)

def process_queue():
    """处理通知队列"""
    center = get_notification_center()
    center.process_queue()

def update_preferences(signal, action):
    """更新用户偏好"""
    center = get_notification_center()
    center.update_preferences(signal, action)

def get_stats():
    """获取统计信息"""
    center = get_notification_center()
    return center.get_stats()
