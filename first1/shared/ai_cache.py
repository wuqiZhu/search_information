# -*- coding: utf-8 -*-
"""
AI 响应缓存模块

基于文件的缓存系统，避免重复调用 AI API，节省 30-50% API 费用。

使用方式:
    from shared.ai_cache import get_ai_cache

    cache = get_ai_cache()

    # 尝试从缓存获取
    cached = cache.get(prompt_hash)
    if cached:
        return cached

    # 缓存未命中，调用 API
    result = call_api(prompt)

    # 存入缓存
    cache.set(prompt_hash, result)
    return result
"""

import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


class AICache:
    """AI 响应缓存"""

    def __init__(
        self,
        cache_dir: str = None,
        max_age_days: int = 30,
        max_size_mb: int = 500,
        enabled: bool = True,
    ):
        """
        初始化缓存

        Args:
            cache_dir: 缓存目录路径
            max_age_days: 缓存最大保留天数
            max_size_mb: 缓存最大大小(MB)
            enabled: 是否启用缓存
        """
        self.enabled = enabled
        self.max_age_days = max_age_days
        self.max_size_mb = max_size_mb

        if cache_dir is None:
            cache_dir = os.environ.get("AI_CACHE_DIR", "/tmp/ai_cache")

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 统计信息
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "errors": 0,
        }

    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        # 使用前两位作为子目录，避免单目录文件过多
        subdir = self.cache_dir / key[:2]
        subdir.mkdir(exist_ok=True)
        return subdir / f"{key}.json"

    def _hash_key(self, prompt: str, model: str = "", **kwargs) -> str:
        """生成缓存键的哈希"""
        # 将 prompt、model 和其他参数组合
        cache_input = {
            "prompt": prompt,
            "model": model,
            **{k: v for k, v in sorted(kwargs.items()) if k not in ["temperature", "max_tokens"]}
        }
        cache_str = json.dumps(cache_input, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(cache_str.encode()).hexdigest()[:16]

    def get(self, prompt: str, model: str = "", **kwargs) -> Optional[Any]:
        """
        从缓存获取响应

        Args:
            prompt: 用户输入的 prompt
            model: 模型名称
            **kwargs: 其他参数（如 temperature 等）

        Returns:
            缓存的响应，如果未命中返回 None
        """
        if not self.enabled:
            return None

        try:
            key = self._hash_key(prompt, model, **kwargs)
            cache_path = self._get_cache_path(key)

            if not cache_path.exists():
                self._stats["misses"] += 1
                return None

            # 读取缓存
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # 检查是否过期
            cached_time = datetime.fromisoformat(cache_data.get("timestamp", "2000-01-01"))
            if datetime.now() - cached_time > timedelta(days=self.max_age_days):
                # 过期，删除缓存
                cache_path.unlink(missing_ok=True)
                self._stats["misses"] += 1
                return None

            self._stats["hits"] += 1
            return cache_data.get("response")

        except Exception as e:
            self._stats["errors"] += 1
            return None

    def set(self, prompt: str, response: Any, model: str = "", **kwargs):
        """
        存入缓存

        Args:
            prompt: 用户输入的 prompt
            response: AI 响应
            model: 模型名称
            **kwargs: 其他参数
        """
        if not self.enabled:
            return

        try:
            key = self._hash_key(prompt, model, **kwargs)
            cache_path = self._get_cache_path(key)

            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt[:200],  # 只保存前200字符用于调试
                "model": model,
                "response": response,
                "key": key,
            }

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            self._stats["sets"] += 1

        except Exception as e:
            self._stats["errors"] += 1

    def delete(self, prompt: str, model: str = "", **kwargs):
        """删除指定缓存"""
        try:
            key = self._hash_key(prompt, model, **kwargs)
            cache_path = self._get_cache_path(key)
            cache_path.unlink(missing_ok=True)
        except Exception:
            pass

    def clear(self, max_age_days: int = None):
        """
        清理过期缓存

        Args:
            max_age_days: 最大保留天数，None 使用默认值
        """
        if max_age_days is None:
            max_age_days = self.max_age_days

        cutoff = datetime.now() - timedelta(days=max_age_days)
        deleted = 0

        for cache_file in self.cache_dir.rglob("*.json"):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                cached_time = datetime.fromisoformat(data.get("timestamp", "2000-01-01"))
                if cached_time < cutoff:
                    cache_file.unlink()
                    deleted += 1
            except Exception:
                # 无法解析的文件直接删除
                cache_file.unlink(missing_ok=True)
                deleted += 1

        return deleted

    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0

        # 计算缓存大小
        total_size = sum(f.stat().st_size for f in self.cache_dir.rglob("*.json"))
        total_files = sum(1 for _ in self.cache_dir.rglob("*.json"))

        return {
            **self._stats,
            "total_requests": total,
            "hit_rate": f"{hit_rate:.1f}%",
            "cache_size_mb": f"{total_size / 1024 / 1024:.2f}",
            "cache_files": total_files,
        }

    def cleanup_if_needed(self):
        """如果缓存过大，自动清理最旧的文件"""
        total_size_mb = sum(f.stat().st_size for f in self.cache_dir.rglob("*.json")) / 1024 / 1024

        if total_size_mb > self.max_size_mb:
            # 按修改时间排序，删除最旧的
            files = sorted(self.cache_dir.rglob("*.json"), key=lambda f: f.stat().st_mtime)

            while total_size_mb > self.max_size_mb * 0.8 and files:
                oldest = files.pop(0)
                size_mb = oldest.stat().st_size / 1024 / 1024
                oldest.unlink(missing_ok=True)
                total_size_mb -= size_mb


# 全局缓存实例
_global_cache: Optional[AICache] = None


def reset_cache():
    """重置全局缓存实例（用于测试）"""
    global _global_cache
    _global_cache = None


def get_ai_cache(
    cache_dir: str = None,
    max_age_days: int = 30,
    max_size_mb: int = 500,
) -> AICache:
    """
    获取全局 AI 缓存实例

    Args:
        cache_dir: 缓存目录
        max_age_days: 最大保留天数
        max_size_mb: 最大缓存大小(MB)

    Returns:
        AICache 实例
    """
    global _global_cache

    if _global_cache is None:
        # 从环境变量读取配置
        enabled = os.environ.get("AI_CACHE_ENABLED", "true").lower() == "true"
        cache_dir = cache_dir or os.environ.get("AI_CACHE_DIR", "/tmp/ai_cache")
        max_age_days = int(os.environ.get("AI_CACHE_MAX_AGE_DAYS", str(max_age_days)))
        max_size_mb = int(os.environ.get("AI_CACHE_MAX_SIZE_MB", str(max_size_mb)))

        _global_cache = AICache(
            cache_dir=cache_dir,
            max_age_days=max_age_days,
            max_size_mb=max_size_mb,
            enabled=enabled,
        )

    return _global_cache


def cached_ai_call(
    prompt: str,
    model: str = "",
    call_func: callable = None,
    **kwargs
) -> Any:
    """
    带缓存的 AI 调用封装

    Args:
        prompt: 用户输入
        model: 模型名称
        call_func: 实际调用 AI 的函数
        **kwargs: 传递给 call_func 的参数

    Returns:
        AI 响应
    """
    cache = get_ai_cache()

    # 尝试从缓存获取
    cached = cache.get(prompt, model, **kwargs)
    if cached is not None:
        return cached

    # 缓存未命中，调用 API
    if call_func is None:
        raise ValueError("call_func is required when cache miss")

    result = call_func(prompt, **kwargs)

    # 存入缓存
    if result is not None:
        cache.set(prompt, result, model, **kwargs)
        # 定期清理
        cache.cleanup_if_needed()

    return result


# 使用示例
if __name__ == "__main__":
    # 测试缓存
    cache = get_ai_cache("/tmp/test_ai_cache")

    # 设置缓存
    cache.set("test prompt", {"result": "test response"}, model="test-model")

    # 获取缓存
    result = cache.get("test prompt", model="test-model")
    print(f"缓存结果: {result}")

    # 统计信息
    stats = cache.get_stats()
    print(f"缓存统计: {stats}")
