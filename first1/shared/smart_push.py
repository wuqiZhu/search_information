# -*- coding: utf-8 -*-
"""
智能推送引擎

根据用户持仓和兴趣，过滤噪音，推送真正相关的信息。

功能：
1. 持仓相关性过滤
2. 情绪阈值触发
3. 推送频率控制
4. 多渠道分发

使用方式:
    from shared.smart_push import SmartPushEngine

    engine = SmartPushEngine()
    should_push = engine.should_push(news, user_profile)
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """用户画像"""
    # 持仓
    holdings: List[str] = field(default_factory=list)  # 股票/基金代码
    watchlist: List[str] = field(default_factory=list)  # 关注列表

    # 兴趣标签
    interest_tags: List[str] = field(default_factory=list)

    # 推送偏好
    push_enabled: bool = True
    min_sentiment_score: float = 0.6  # 情绪阈值
    min_relevance_score: float = 0.5  # 相关性阈值
    max_push_per_hour: int = 10  # 每小时最大推送数
    quiet_hours: tuple = (23, 8)  # 免打扰时间

    # 统计
    push_count_today: int = 0
    last_push_time: float = 0


@dataclass
class NewsItem:
    """新闻条目"""
    id: str
    title: str
    content: str
    source: str
    url: str
    published_at: datetime = field(default_factory=datetime.now)

    # AI 分析结果
    sentiment: str = ""  # positive/negative/neutral
    sentiment_score: float = 0.0
    category: str = ""
    keywords: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
    investment_impact: str = ""


class SmartPushEngine:
    """智能推送引擎"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.push_history: Dict[str, List[float]] = {}  # user_id -> [timestamp]
        self.news_cache: Dict[str, NewsItem] = {}

        # 默认配置
        self.min_sentiment_score = self.config.get("min_sentiment_score", 0.6)
        self.min_relevance_score = self.config.get("min_relevance_score", 0.5)
        self.max_push_per_hour = self.config.get("max_push_per_hour", 10)
        self.quiet_hours = self.config.get("quiet_hours", (23, 8))

    def should_push(
        self,
        news: NewsItem,
        user: UserProfile,
        current_time: datetime = None,
    ) -> Dict[str, Any]:
        """
        判断是否应该推送

        Returns:
            {
                "should_push": bool,
                "reason": str,
                "relevance_score": float,
                "priority": str,  # high/medium/low
            }
        """
        if current_time is None:
            current_time = datetime.now()

        result = {
            "should_push": False,
            "reason": "",
            "relevance_score": 0.0,
            "priority": "low",
        }

        # 1. 检查推送是否启用
        if not user.push_enabled:
            result["reason"] = "推送已禁用"
            return result

        # 2. 检查免打扰时间
        hour = current_time.hour
        quiet_start, quiet_end = self.quiet_hours
        if quiet_start > quiet_end:
            # 跨午夜
            if hour >= quiet_start or hour < quiet_end:
                result["reason"] = "免打扰时间"
                return result
        else:
            if quiet_start <= hour < quiet_end:
                result["reason"] = "免打扰时间"
                return result

        # 3. 检查推送频率
        user_id = id(user)
        if user_id not in self.push_history:
            self.push_history[user_id] = []

        # 清理过期记录
        one_hour_ago = time.time() - 3600
        self.push_history[user_id] = [
            t for t in self.push_history[user_id] if t > one_hour_ago
        ]

        if len(self.push_history[user_id]) >= user.max_push_per_hour:
            result["reason"] = "推送频率超限"
            return result

        # 4. 计算相关性分数
        relevance_score = self._calculate_relevance(news, user)
        result["relevance_score"] = relevance_score

        # 5. 检查相关性阈值
        min_relevance = max(user.min_relevance_score, self.min_relevance_score)
        if relevance_score < min_relevance:
            result["reason"] = f"相关性不足: {relevance_score:.2f} < {min_relevance}"
            return result

        # 6. 检查情绪阈值
        if news.sentiment_score > 0:
            min_sentiment = max(user.min_sentiment_score, self.min_sentiment_score)
            if news.sentiment_score < min_sentiment:
                result["reason"] = f"情绪强度不足: {news.sentiment_score:.2f} < {min_sentiment}"
                return result

        # 7. 确定优先级
        priority = self._calculate_priority(news, relevance_score)
        result["priority"] = priority

        # 8. 通过所有检查，应该推送
        result["should_push"] = True
        result["reason"] = f"相关性: {relevance_score:.2f}, 情绪: {news.sentiment_score:.2f}"

        return result

    def _calculate_relevance(self, news: NewsItem, user: UserProfile) -> float:
        """计算相关性分数"""
        score = 0.0
        max_score = 0.0

        # 1. 持仓相关 (权重最高)
        if user.holdings:
            max_score += 0.5
            holding_keywords = set(user.holdings)
            news_keywords = set(news.keywords)

            # 检查标题和内容中是否包含持仓相关关键词
            text = f"{news.title} {news.content}".lower()
            for holding in holding_keywords:
                if holding.lower() in text:
                    score += 0.5
                    break

        # 2. 关注列表相关
        if user.watchlist:
            max_score += 0.3
            text = f"{news.title} {news.content}".lower()
            for item in user.watchlist:
                if item.lower() in text:
                    score += 0.3
                    break

        # 3. 兴趣标签相关
        if user.interest_tags:
            max_score += 0.2
            news_tags = set(news.keywords) | {news.category}
            user_tags = set(user.interest_tags)
            overlap = len(news_tags & user_tags)
            if overlap > 0:
                score += min(0.2, overlap * 0.1)

        # 归一化
        if max_score > 0:
            score = score / max_score

        return min(1.0, score)

    def _calculate_priority(self, news: NewsItem, relevance_score: float) -> str:
        """计算推送优先级"""
        # 高优先级条件
        if (
            relevance_score > 0.8
            or news.sentiment_score > 0.9
            or news.category in ["01-公司财报", "02-重大公告"]
        ):
            return "high"

        # 中优先级条件
        if relevance_score > 0.6 or news.sentiment_score > 0.7:
            return "medium"

        return "low"

    def record_push(self, user: UserProfile, news: NewsItem):
        """记录推送"""
        user_id = id(user)
        if user_id not in self.push_history:
            self.push_history[user_id] = []
        self.push_history[user_id].append(time.time())

        user.push_count_today += 1
        user.last_push_time = time.time()

    def filter_news_batch(
        self,
        news_list: List[NewsItem],
        user: UserProfile,
        current_time: datetime = None,
    ) -> List[Dict[str, Any]]:
        """批量过滤新闻"""
        results = []

        for news in news_list:
            result = self.should_push(news, user, current_time)
            if result["should_push"]:
                results.append({
                    "news": news,
                    "relevance_score": result["relevance_score"],
                    "priority": result["priority"],
                })

        # 按优先级和相关性排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        results.sort(
            key=lambda x: (priority_order.get(x["priority"], 2), -x["relevance_score"])
        )

        return results

    def generate_push_message(
        self,
        news: NewsItem,
        relevance_score: float,
        priority: str,
    ) -> Dict[str, str]:
        """生成推送消息"""
        # 情绪图标
        sentiment_icon = {
            "positive": "🟢",
            "negative": "🔴",
            "neutral": "⚪",
        }.get(news.sentiment, "⚪")

        # 优先级标签
        priority_tag = {
            "high": "🔥 紧急",
            "medium": "📢 重要",
            "low": "ℹ️ 提醒",
        }.get(priority, "ℹ️ 提醒")

        title = f"{priority_tag} {sentiment_icon} {news.title}"

        content = f"""
{news.title}

📌 分类: {news.category}
{sentiment_icon} 情绪: {news.sentiment} ({news.sentiment_score:.0%})
📊 相关性: {relevance_score:.0%}
🏷️ 关键词: {', '.join(news.keywords[:5])}

💡 影响: {news.investment_impact}

🔗 来源: {news.source}
        """.strip()

        return {
            "title": title,
            "content": content,
            "url": news.url,
            "priority": priority,
        }


# 便捷函数
def create_smart_push(config: Dict[str, Any] = None) -> SmartPushEngine:
    """创建智能推送引擎实例"""
    return SmartPushEngine(config)


# 使用示例
if __name__ == "__main__":
    # 创建引擎
    engine = SmartPushEngine()

    # 用户画像
    user = UserProfile(
        holdings=["600519", "000858"],  # 贵州茅台、五粮液
        watchlist=["白酒", "消费"],
        interest_tags=["消费", "白酒", "食品饮料"],
    )

    # 新闻
    news = NewsItem(
        id="1",
        title="贵州茅台Q3净利润超预期，股价创新高",
        content="...",
        source="东方财富",
        url="https://example.com",
        sentiment="positive",
        sentiment_score=0.9,
        category="01-公司财报",
        keywords=["贵州茅台", "净利润", "白酒"],
        investment_impact="短期利好白酒板块",
    )

    # 判断是否推送
    result = engine.should_push(news, user)
    print(f"Should push: {result}")

    # 生成推送消息
    if result["should_push"]:
        message = engine.generate_push_message(
            news, result["relevance_score"], result["priority"]
        )
        print(f"Push message: {message}")
