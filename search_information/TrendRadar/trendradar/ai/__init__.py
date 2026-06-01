# coding=utf-8
"""
TrendRadar AI 模块

提供 AI 大模型对热点新闻的深度分析、翻译和个性化解读功能
"""

from .analyzer import AIAnalyzer, AIAnalysisResult
from .translator import AITranslator, TranslationResult, BatchTranslationResult
from .personalized import (
    UserProfile,
    PersonalizedInsight,
    PersonalizedAnalyzer,
    render_personalized_html,
    render_personalized_markdown,
)
from .formatter import (
    get_ai_analysis_renderer,
    render_ai_analysis_markdown,
    render_ai_analysis_feishu,
    render_ai_analysis_dingtalk,
    render_ai_analysis_html,
    render_ai_analysis_html_rich,
    render_ai_analysis_plain,
)

__all__ = [
    # 分析器
    "AIAnalyzer",
    "AIAnalysisResult",
    # 翻译器
    "AITranslator",
    "TranslationResult",
    "BatchTranslationResult",
    # 个性化解读
    "UserProfile",
    "PersonalizedInsight",
    "PersonalizedAnalyzer",
    "render_personalized_html",
    "render_personalized_markdown",
    # 格式化
    "get_ai_analysis_renderer",
    "render_ai_analysis_markdown",
    "render_ai_analysis_feishu",
    "render_ai_analysis_dingtalk",
    "render_ai_analysis_html",
    "render_ai_analysis_html_rich",
    "render_ai_analysis_plain",
]
