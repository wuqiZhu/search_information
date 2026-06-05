"""AI 语义过滤模块

对关键词匹配的结果进行二次过滤：
- 判断新闻与关键词的相关性（0-10分）
- 判断新闻的重要性（是否值得推送）
- 过滤标题党、软文、广告

使用方式：
    from trendradar.ai.semantic_filter import SemanticFilter

    filter = SemanticFilter(ai_client)
    filtered = filter.filter_news(matched_news, min_relevance=6)
"""

import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

FILTER_PROMPT = """你是一个新闻相关性评估专家。请评估以下新闻标题与用户关注领域的相关性。

用户关注的领域：
{user_interests}

请对每条新闻评分（0-10分），评估标准：
1. 相关性（0-10）：与用户关注领域的关联程度
2. 重要性（0-10）：对用户的价值（是否值得花时间阅读）
3. 是否标题党（true/false）：标题夸张但内容空洞

请以 JSON 数组格式返回，每个元素包含：
- index: 新闻序号
- relevance: 相关性分数（0-10）
- importance: 重要性分数（0-10）
- is_clickbait: 是否标题党
- reason: 简短理由（10字以内）

新闻列表：
{news_list}

只返回 JSON 数组，不要其他内容。"""


class SemanticFilter:
    """AI 语义过滤器"""

    def __init__(self, ai_client, min_relevance: int = 6, min_importance: int = 5):
        """
        初始化语义过滤器

        Args:
            ai_client: AI 客户端实例（trendradar.ai.client.AIClient）
            min_relevance: 最低相关性阈值（0-10）
            min_importance: 最低重要性阈值（0-10）
        """
        self.ai_client = ai_client
        self.min_relevance = min_relevance
        self.min_importance = min_importance

    def filter_news(self, news_list: List[Dict[str, Any]],
                    user_interests: str = None,
                    min_relevance: int = None,
                    min_importance: int = None) -> List[Dict[str, Any]]:
        """
        过滤新闻列表

        Args:
            news_list: 新闻列表，每条需包含 title 字段
            user_interests: 用户关注领域描述（可选）
            min_relevance: 最低相关性阈值（覆盖默认值）
            min_importance: 最低重要性阈值（覆盖默认值）

        Returns:
            过滤后的新闻列表，添加了 ai_relevance、ai_importance、ai_reason 字段
        """
        if not news_list:
            return []

        if not self.ai_client:
            logger.warning("AI 客户端未初始化，跳过语义过滤")
            return news_list

        threshold_r = min_relevance if min_relevance is not None else self.min_relevance
        threshold_i = min_importance if min_importance is not None else self.min_importance

        interests = user_interests or "嵌入式开发、AI、芯片、自动驾驶、机器人、求职、学生优惠、实习、投资"

        # 构建新闻列表文本
        news_text = ""
        for i, news in enumerate(news_list):
            title = news.get("title", news.get("name", ""))
            source = news.get("source", news.get("platform", ""))
            news_text += f"{i+1}. [{source}] {title}\n"

        # 构建 prompt
        prompt = FILTER_PROMPT.format(
            user_interests=interests,
            news_list=news_text
        )

        try:
            response = self.ai_client.chat([
                {"role": "user", "content": prompt}
            ])

            # 解析 AI 返回的 JSON
            scores = self._parse_response(response, len(news_list))

            # 过滤并添加评分
            filtered = []
            for i, news in enumerate(news_list):
                if i < len(scores):
                    score = scores[i]
                    news["ai_relevance"] = score.get("relevance", 5)
                    news["ai_importance"] = score.get("importance", 5)
                    news["ai_is_clickbait"] = score.get("is_clickbait", False)
                    news["ai_reason"] = score.get("reason", "")

                    # 应用过滤
                    if news["ai_relevance"] >= threshold_r and \
                       news["ai_importance"] >= threshold_i and \
                       not news["ai_is_clickbait"]:
                        filtered.append(news)
                else:
                    # AI 没有返回评分的新闻保留
                    filtered.append(news)

            logger.info(f"语义过滤: {len(news_list)} -> {len(filtered)} 条"
                        f"(阈值: relevance>={threshold_r}, importance>={threshold_i})")
            return filtered

        except Exception as e:
            logger.error(f"语义过滤失败: {e}，返回原始列表")
            return news_list

    def score_news(self, news_list: List[Dict[str, Any]],
                   user_interests: str = None) -> List[Dict[str, Any]]:
        """
        对新闻评分但不过滤

        Args:
            news_list: 新闻列表
            user_interests: 用户关注领域描述

        Returns:
            添加了评分字段的新闻列表
        """
        if not news_list or not self.ai_client:
            return news_list

        interests = user_interests or "嵌入式开发、AI、芯片、自动驾驶、机器人、求职、学生优惠、实习、投资"

        news_text = ""
        for i, news in enumerate(news_list):
            title = news.get("title", news.get("name", ""))
            source = news.get("source", news.get("platform", ""))
            news_text += f"{i+1}. [{source}] {title}\n"

        prompt = FILTER_PROMPT.format(
            user_interests=interests,
            news_list=news_text
        )

        try:
            response = self.ai_client.chat([
                {"role": "user", "content": prompt}
            ])

            scores = self._parse_response(response, len(news_list))

            for i, news in enumerate(news_list):
                if i < len(scores):
                    score = scores[i]
                    news["ai_relevance"] = score.get("relevance", 5)
                    news["ai_importance"] = score.get("importance", 5)
                    news["ai_is_clickbait"] = score.get("is_clickbait", False)
                    news["ai_reason"] = score.get("reason", "")

            return news_list

        except Exception as e:
            logger.error(f"AI 评分失败: {e}")
            return news_list

    def _parse_response(self, response: str, expected_count: int) -> List[Dict]:
        """解析 AI 返回的 JSON"""
        # 尝试提取 JSON 数组
        response = response.strip()

        # 如果包含 markdown 代码块，提取其中的 JSON
        if "```" in response:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                response = response[start:end]

        try:
            scores = json.loads(response)
            if isinstance(scores, list):
                return scores
        except json.JSONDecodeError:
            pass

        # 尝试逐行解析
        try:
            # 有时 AI 会返回带注释的 JSON
            lines = response.split('\n')
            json_lines = [l for l in lines if l.strip().startswith('{') or l.strip().startswith('[')]
            if json_lines:
                json_str = ''.join(json_lines)
                scores = json.loads(json_str)
                if isinstance(scores, list):
                    return scores
        except Exception:
            pass

        logger.warning(f"无法解析 AI 响应: {response[:200]}")
        return [{"relevance": 5, "importance": 5, "is_clickbait": False, "reason": "解析失败"} for _ in range(expected_count)]
