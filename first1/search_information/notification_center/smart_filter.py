# -*- coding: utf-8 -*-
"""
智能通知过滤模块

功能：
1. 消息去重 - 相同内容短时间内不重复发送
2. 消息聚合 - 同类新闻合并发送
3. 优先级分级 - 重要消息立即推送，普通消息汇总
4. 关键词过滤 - 根据关键词决定推送策略
"""

import hashlib
import time
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


class SmartFilter:
    """智能通知过滤器"""

    def __init__(self, config: Dict = None):
        self.config = config or {}

        # 消息历史（用于去重）
        # key: content_hash, value: last_sent_timestamp
        self.message_history: Dict[str, float] = {}
        self.history_ttl = self.config.get('history_ttl_seconds', 3600)  # 1小时

        # 聚合队列
        # key: aggregate_key, value: [messages]
        self.aggregate_queue: Dict[str, List[Dict]] = defaultdict(list)
        self.aggregate_interval = self.config.get('aggregate_interval_seconds', 300)  # 5分钟
        self.last_aggregate_time: Dict[str, float] = {}

        # 高优先级关键词
        self.high_priority_keywords = self.config.get('high_priority_keywords', [
            '暴跌', '崩盘', '危机', '风险预警', '紧急', '突发',
            '涨停', '跌停', '大幅上涨', '大幅下跌',
            '央行', '降准', '降息', '加息',
            '持仓', '持仓基金',
        ])

        # 低优先级关键词（可忽略或汇总）
        self.low_priority_keywords = self.config.get('low_priority_keywords', [
            '日常', '常规', '普通',
        ])

        # 静默关键词（匹配则不推送）
        self.silent_keywords = self.config.get('silent_keywords', [
            '测试', 'test', '调试',
        ])

    def _compute_hash(self, text: str) -> str:
        """计算内容哈希"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:16]

    def _is_duplicate(self, content_hash: str) -> bool:
        """检查是否重复消息"""
        now = time.time()
        last_sent = self.message_history.get(content_hash)

        if last_sent and (now - last_sent) < self.history_ttl:
            return True

        return False

    def _record_sent(self, content_hash: str):
        """记录已发送"""
        self.message_history[content_hash] = time.time()
        self._cleanup_history()

    def _cleanup_history(self):
        """清理过期的历史记录"""
        now = time.time()
        expired = [k for k, v in self.message_history.items() if now - v > self.history_ttl]
        for k in expired:
            del self.message_history[k]

    def determine_priority(self, text: str, tags: List[str] = None) -> str:
        """
        根据内容确定优先级

        Returns:
            "urgent" | "high" | "medium" | "low"
        """
        text_lower = text.lower()
        tags = tags or []

        # 检查静默关键词
        for keyword in self.silent_keywords:
            if keyword.lower() in text_lower:
                return "silent"

        # 检查高优先级关键词
        for keyword in self.high_priority_keywords:
            if keyword in text:
                return "high"

        # 检查标签
        if "urgent" in tags or "紧急" in tags:
            return "urgent"
        if "important" in tags or "重要" in tags:
            return "high"

        # 检查低优先级关键词
        for keyword in self.low_priority_keywords:
            if keyword in text:
                return "low"

        # 默认中优先级
        return "medium"

    def get_aggregate_key(self, message: Dict) -> str:
        """
        获取消息的聚合键

        同一聚合键的消息会被合并发送
        """
        source = message.get('source', 'unknown')
        priority = message.get('priority', 'medium')

        # 高优先级不聚合
        if priority in ('urgent', 'high'):
            return None

        # 按来源和小时聚合
        hour_key = datetime.now().strftime("%Y%m%d%H")
        return f"{source}_{priority}_{hour_key}"

    def should_send_immediately(self, message: Dict) -> Tuple[bool, str]:
        """
        判断是否立即发送

        Returns:
            (should_send, reason)
        """
        text = message.get('text', '')
        priority = message.get('priority', 'medium')
        tags = message.get('tags', [])

        # 计算内容哈希
        content_hash = self._compute_hash(text)

        # 检查是否重复
        if self._is_duplicate(content_hash):
            return False, "duplicate"

        # 检查静默
        determined_priority = self.determine_priority(text, tags)
        if determined_priority == "silent":
            return False, "silent"

        # 紧急和高优先级立即发送
        if priority in ('urgent', 'high') or determined_priority in ('urgent', 'high'):
            self._record_sent(content_hash)
            return True, "high_priority"

        # 中低优先级聚合
        aggregate_key = self.get_aggregate_key(message)
        if aggregate_key:
            self.aggregate_queue[aggregate_key].append(message)
            # 检查是否到了发送时间
            last_time = self.last_aggregate_time.get(aggregate_key, 0)
            if time.time() - last_time >= self.aggregate_interval:
                self.last_aggregate_time[aggregate_key] = time.time()
                return True, "aggregate_ready"
            return False, "queued"

        self._record_sent(content_hash)
        return True, "normal"

    def get_aggregated_messages(self) -> List[Dict]:
        """获取待发送的聚合消息"""
        now = time.time()
        result = []

        for key, messages in list(self.aggregate_queue.items()):
            last_time = self.last_aggregate_time.get(key, 0)
            if now - last_time >= self.aggregate_interval and messages:
                # 聚合消息
                aggregated = self._aggregate_messages(key, messages)
                result.append(aggregated)
                self.aggregate_queue[key] = []
                self.last_aggregate_time[key] = now

        return result

    def _aggregate_messages(self, key: str, messages: List[Dict]) -> Dict:
        """聚合多条消息为一条"""
        source = messages[0].get('source', '未知')
        count = len(messages)

        # 提取标题
        titles = []
        for msg in messages[:10]:
            title = msg.get('title', '')
            if not title:
                # 从文本提取第一行作为标题
                text = msg.get('text', '')
                title = text.split('\n')[0][:50]
            titles.append(title)

        # 构建聚合消息
        lines = [
            f"## 📊 {source} 汇总 ({count}条)",
            "",
        ]

        for i, title in enumerate(titles, 1):
            lines.append(f"{i}. {title}")

        if count > 10:
            lines.append(f"\n...还有 {count - 10} 条")

        lines.append(f"\n⏰ 时间: {datetime.now().strftime('%H:%M')}")

        return {
            'text': '\n'.join(lines),
            'title': f"{source} 汇总",
            'priority': 'medium',
            'source': source,
            'channel': 'dingtalk',
            'tags': ['aggregated'],
            'count': count,
        }

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'history_size': len(self.message_history),
            'queue_size': sum(len(msgs) for msgs in self.aggregate_queue.values()),
            'queue_keys': list(self.aggregate_queue.keys()),
        }


# 全局实例
_filter_instance = None


def get_smart_filter(config: Dict = None) -> SmartFilter:
    """获取全局智能过滤器实例"""
    global _filter_instance
    if _filter_instance is None:
        _filter_instance = SmartFilter(config)
    return _filter_instance
