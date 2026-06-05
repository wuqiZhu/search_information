# -*- coding: utf-8 -*-
"""
AI 缓存模块测试
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.ai_cache import AICache, get_ai_cache, reset_cache


@pytest.fixture
def temp_cache_dir():
    """创建临时缓存目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def cache(temp_cache_dir):
    """创建缓存实例"""
    return AICache(cache_dir=temp_cache_dir, max_age_days=7, max_size_mb=10)


class TestAICache:
    """AI 缓存测试"""

    def test_set_and_get(self, cache):
        """测试设置和获取缓存"""
        prompt = "测试提示词"
        response = {"result": "测试结果"}

        cache.set(prompt, response, model="test-model")
        result = cache.get(prompt, model="test-model")

        assert result == response

    def test_cache_miss(self, cache):
        """测试缓存未命中"""
        result = cache.get("不存在的提示词", model="test-model")
        assert result is None

    def test_cache_disabled(self, temp_cache_dir):
        """测试禁用缓存"""
        cache = AICache(cache_dir=temp_cache_dir, enabled=False)

        cache.set("test", "value")
        result = cache.get("test")

        assert result is None

    def test_different_models(self, cache):
        """测试不同模型的缓存隔离"""
        prompt = "相同提示词"

        cache.set(prompt, "model_a_result", model="model-a")
        cache.set(prompt, "model_b_result", model="model-b")

        assert cache.get(prompt, model="model-a") == "model_a_result"
        assert cache.get(prompt, model="model-b") == "model_b_result"

    def test_delete(self, cache):
        """测试删除缓存"""
        prompt = "要删除的提示词"
        cache.set(prompt, "value")

        cache.delete(prompt)
        result = cache.get(prompt)

        assert result is None

    def test_stats(self, cache):
        """测试统计信息"""
        cache.set("prompt1", "value1")
        cache.set("prompt2", "value2")
        cache.get("prompt1")
        cache.get("prompt3")

        stats = cache.get_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["sets"] == 2
        assert stats["cache_files"] == 2

    def test_cleanup(self, cache):
        """测试清理过期缓存"""
        # 创建一个过期的缓存文件
        old_time = datetime.now() - timedelta(days=10)
        cache.set("old_prompt", "old_value")

        # 手动修改文件时间
        for cache_file in cache.cache_dir.rglob("*.json"):
            with open(cache_file, "r") as f:
                data = json.load(f)
            data["timestamp"] = old_time.isoformat()
            with open(cache_file, "w") as f:
                json.dump(data, f)

        # 创建一个新的缓存
        cache.set("new_prompt", "new_value")

        # 清理过期缓存
        deleted = cache.clear(max_age_days=7)

        assert deleted == 1
        assert cache.get("old_prompt") is None
        assert cache.get("new_prompt") == "new_value"


class TestGlobalCache:
    """全局缓存测试"""

    def test_singleton(self, temp_cache_dir):
        """测试单例模式"""
        reset_cache()
        cache1 = get_ai_cache(cache_dir=temp_cache_dir)
        cache2 = get_ai_cache(cache_dir=temp_cache_dir)

        assert cache1 is cache2

    def test_reset(self, temp_cache_dir):
        """测试重置"""
        reset_cache()
        cache1 = get_ai_cache(cache_dir=temp_cache_dir)
        reset_cache()
        cache2 = get_ai_cache(cache_dir=temp_cache_dir)

        assert cache1 is not cache2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
