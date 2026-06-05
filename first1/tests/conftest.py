# -*- coding: utf-8 -*-
"""
pytest 配置文件

提供共享的 fixtures 和配置。
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """设置测试环境"""
    # 设置测试环境变量
    os.environ["APP_ENV"] = "testing"
    os.environ["APP_DEBUG"] = "true"
    os.environ["LOG_LEVEL"] = "DEBUG"
    os.environ["AI_CACHE_ENABLED"] = "false"  # 测试时禁用缓存

    yield

    # 清理
    os.environ.pop("APP_ENV", None)
    os.environ.pop("APP_DEBUG", None)
    os.environ.pop("LOG_LEVEL", None)
    os.environ.pop("AI_CACHE_ENABLED", None)


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_root():
    """获取项目根目录"""
    return PROJECT_ROOT


@pytest.fixture
def sample_news_item():
    """示例新闻数据"""
    return {
        "title": "某光伏龙头Q3净利润暴增340%",
        "source": "东方财富",
        "url": "https://example.com/news/1",
        "published_at": "2026-06-02 10:00:00",
        "summary": "某光伏龙头企业发布Q3财报，净利润同比增长340%。",
    }


@pytest.fixture
def sample_analysis_result():
    """示例分析结果"""
    return {
        "sentiment": "positive",
        "sentiment_score": 0.85,
        "category": "01-公司财报",
        "keywords": ["光伏", "净利润", "增长"],
        "summary": "光伏龙头企业Q3业绩超预期，净利润大幅增长。",
        "investment_impact": "短期利好光伏板块，关注相关产业链机会。",
    }
