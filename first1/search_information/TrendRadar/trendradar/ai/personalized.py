# coding=utf-8
"""
个性化解读模块

基于用户画像，为新闻生成"这对你意味着什么"的个性化解读
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from trendradar.ai.client import AIClient


@dataclass
class UserProfile:
    """用户画像"""
    # 基础身份
    roles: List[str] = field(default_factory=lambda: ["学生", "投资者", "公众"])

    # 职业方向
    career_fields: List[str] = field(default_factory=lambda: [
        "嵌入式Linux", "Linux应用开发", "C/C++开发", "物联网"
    ])

    # 投资偏好
    investment_interests: List[str] = field(default_factory=lambda: [
        "科技股", "半导体", "新能源", "AI", "消费电子"
    ])

    # 关注领域
    focus_areas: List[str] = field(default_factory=lambda: [
        "技术趋势", "政策红利", "职业发展", "消费省钱"
    ])

    # 自定义描述
    custom_description: str = ""


@dataclass
class PersonalizedInsight:
    """个性化解读结果"""
    headline: str = ""           # 核心要点（一句话）
    impact_areas: List[Dict] = field(default_factory=list)  # 影响领域列表
    action_items: List[str] = field(default_factory=list)   # 行动建议
    raw_response: str = ""       # 原始响应
    success: bool = False        # 是否成功
    error: str = ""              # 错误信息


class PersonalizedAnalyzer:
    """个性化解读分析器"""

    def __init__(
        self,
        ai_config: Dict[str, Any],
        user_profile: Optional[UserProfile] = None,
        language: str = "Chinese",
    ):
        """
        初始化个性化解读分析器

        Args:
            ai_config: AI 模型配置
            user_profile: 用户画像
            language: 输出语言
        """
        self.ai_config = ai_config
        self.user_profile = user_profile or UserProfile()
        self.language = language

        # 创建 AI 客户端
        self.client = AIClient(ai_config)

    def _build_user_profile_text(self) -> str:
        """构建用户画像文本"""
        profile = self.user_profile
        parts = []

        if profile.roles:
            parts.append(f"身份角色：{'、'.join(profile.roles)}")

        if profile.career_fields:
            parts.append(f"职业方向：{'、'.join(profile.career_fields)}")

        if profile.investment_interests:
            parts.append(f"投资偏好：{'、'.join(profile.investment_interests)}")

        if profile.focus_areas:
            parts.append(f"关注领域：{'、'.join(profile.focus_areas)}")

        if profile.custom_description:
            parts.append(f"个人描述：{profile.custom_description}")

        return "\n".join(parts)

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是一名**个性化新闻解读专家**。你的任务是根据用户的个人画像，分析新闻对用户的具体影响。

## 核心原则

1. **身份视角**：从用户的具体身份（学生/职场人/投资者）出发分析影响
2. **关联性**：明确说明新闻与用户职业、投资、生活的具体关联
3. **可操作性**：给出具体、可执行的建议，而非泛泛而谈
4. **简洁性**：每条解读控制在 2-3 句话，直击要害

## 输出要求

- 使用 {language} 输出
- 语言通俗易懂，避免专业术语堆砌
- 每个影响领域独立分析，不重复
- 行动建议要具体，如"关注XX股票"、"学习XX技术"、"等待XX政策落地"

## 用户画像
{user_profile}
"""

    def _build_user_prompt(self, news_title: str, news_context: str = "") -> str:
        """构建用户提示词"""
        prompt = f"""请根据以下用户画像，分析这条新闻对用户的影响：

## 新闻标题
{news_title}
"""
        if news_context:
            prompt += f"""
## 新闻背景
{news_context}
"""

        prompt += """
请返回 JSON 格式的解读结果：

```json
{
  "headline": "一句话核心要点（15字以内）",
  "impact_areas": [
    {
      "area": "影响领域（如：职业发展/投资机会/学习方向/消费决策）",
      "impact": "具体影响说明（2句话以内）",
      "relevance": "与用户的关联度（high/medium/low）"
    }
  ],
  "action_items": [
    "具体行动建议1",
    "具体行动建议2"
  ]
}
```

要求：
- impact_areas 最多 3 个领域
- action_items 最多 3 条建议
- 必须返回有效的 JSON 格式
"""
        return prompt

    def analyze_news(
        self,
        news_title: str,
        news_context: str = "",
        timeout: int = 30,
    ) -> PersonalizedInsight:
        """
        为单条新闻生成个性化解读

        Args:
            news_title: 新闻标题
            news_context: 新闻背景（可选）
            timeout: 超时时间

        Returns:
            个性化解读结果
        """
        result = PersonalizedInsight()

        system_prompt = self._build_system_prompt().format(
            language=self.language,
            user_profile=self._build_user_profile_text(),
        )

        user_prompt = self._build_user_prompt(news_title, news_context)

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            response_text = self.client.chat_completion(
                messages=messages,
                timeout=timeout,
            )

            result.raw_response = response_text

            # 解析 JSON 响应
            parsed = self._parse_response(response_text)
            if parsed:
                result.headline = parsed.get("headline", "")
                result.impact_areas = parsed.get("impact_areas", [])
                result.action_items = parsed.get("action_items", [])
                result.success = True
            else:
                result.error = "无法解析 AI 响应"

        except Exception as e:
            result.error = str(e)

        return result

    def analyze_batch(
        self,
        news_items: List[Dict],
        max_items: int = 5,
        timeout: int = 60,
    ) -> List[Dict]:
        """
        批量分析新闻的个性化解读

        Args:
            news_items: 新闻列表，每个包含 title 和可选的 summary/url
            max_items: 最多分析的新闻条数
            timeout: 超时时间

        Returns:
            带有个性化解读的新闻列表
        """
        if not news_items:
            return news_items

        # 取前 N 条进行分析
        items_to_analyze = news_items[:max_items]

        # 构建批量分析提示词
        system_prompt = self._build_system_prompt().format(
            language=self.language,
            user_profile=self._build_user_profile_text(),
        )

        # 构建新闻列表
        news_list_text = ""
        for i, item in enumerate(items_to_analyze, 1):
            title = item.get("title", "")
            summary = item.get("summary", "")
            source = item.get("source_name") or item.get("feed_name", "")
            news_list_text += f"\n{i}. 【{source}】{title}"
            if summary:
                news_list_text += f"\n   摘要：{summary[:100]}"

        user_prompt = f"""请根据用户画像，分析以下新闻对用户的影响：

## 新闻列表
{news_list_text}

请返回 JSON 数组格式的解读结果：

```json
[
  {{
    "index": 1,
    "headline": "一句话核心要点",
    "impact_areas": [
      {{
        "area": "影响领域",
        "impact": "具体影响说明",
        "relevance": "high/medium/low"
      }}
    ],
    "action_items": ["行动建议1", "行动建议2"]
  }}
]
```

要求：
- 每条新闻独立分析
- headline 控制在 15 字以内
- impact_areas 最多 2 个领域
- action_items 最多 2 条建议
- 必须返回有效的 JSON 数组
"""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            response_text = self.client.chat_completion(
                messages=messages,
                timeout=timeout,
            )

            # 解析 JSON 响应
            parsed_list = self._parse_response(response_text)
            if isinstance(parsed_list, list):
                # 将解读结果合并到新闻数据中
                for i, insight in enumerate(parsed_list):
                    if i < len(items_to_analyze):
                        idx = insight.get("index", i + 1) - 1
                        if 0 <= idx < len(items_to_analyze):
                            items_to_analyze[idx]["personalized"] = {
                                "headline": insight.get("headline", ""),
                                "impact_areas": insight.get("impact_areas", []),
                                "action_items": insight.get("action_items", []),
                            }

        except Exception as e:
            print(f"[个性化解读] 批量分析失败: {e}")

        return news_items

    def _parse_response(self, response_text: str) -> Optional[Any]:
        """解析 AI 响应中的 JSON"""
        try:
            # 尝试直接解析
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end > start:
                json_str = response_text[start:end].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

        # 尝试从普通代码块中提取
        if "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end > start:
                json_str = response_text[start:end].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

        return None


def render_personalized_html(insight: PersonalizedInsight) -> str:
    """
    渲染个性化解读 HTML

    Args:
        insight: 个性化解读结果

    Returns:
        HTML 字符串
    """
    if not insight.success:
        return ""

    from trendradar.report.helpers import html_escape

    html = '<div class="personalized-insight">'

    # 核心要点
    if insight.headline:
        html += f'<div class="insight-headline">{html_escape(insight.headline)}</div>'

    # 影响领域
    if insight.impact_areas:
        html += '<div class="insight-areas">'
        for area in insight.impact_areas:
            area_name = area.get("area", "")
            impact = area.get("impact", "")
            relevance = area.get("relevance", "medium")

            relevance_class = f"relevance-{relevance}"

            html += f"""
            <div class="insight-area {relevance_class}">
                <div class="insight-area-name">{html_escape(area_name)}</div>
                <div class="insight-area-impact">{html_escape(impact)}</div>
            </div>
            """
        html += '</div>'

    # 行动建议
    if insight.action_items:
        html += '<div class="insight-actions">'
        for action in insight.action_items:
            html += f'<div class="insight-action">→ {html_escape(action)}</div>'
        html += '</div>'

    html += '</div>'

    return html


def render_personalized_markdown(insight: PersonalizedInsight) -> str:
    """
    渲染个性化解读 Markdown（用于钉钉推送）

    Args:
        insight: 个性化解读结果

    Returns:
        Markdown 字符串
    """
    if not insight.success:
        return ""

    lines = []

    # 核心要点
    if insight.headline:
        lines.append(f"💡 **{insight.headline}**")

    # 影响领域
    if insight.impact_areas:
        for area in insight.impact_areas:
            area_name = area.get("area", "")
            impact = area.get("impact", "")
            relevance = area.get("relevance", "medium")

            # 相关度图标
            if relevance == "high":
                icon = "🔴"
            elif relevance == "medium":
                icon = "🟡"
            else:
                icon = "🟢"

            lines.append(f"{icon} **{area_name}**：{impact}")

    # 行动建议
    if insight.action_items:
        lines.append("")
        for action in insight.action_items:
            lines.append(f"→ {action}")

    return "\n".join(lines)
