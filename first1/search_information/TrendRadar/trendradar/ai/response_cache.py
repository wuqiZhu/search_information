# coding=utf-8
"""
AI 响应缓存模块

缓存 AI API 的响应，避免相同或相似的输入重复调用 API。
基于 SQLite，支持 TTL 过期。

原理：
  1. 对 messages + model + temperature 做 SHA256 哈希作为缓存键
  2. 缓存命中且未过期 → 直接返回
  3. 缓存 miss → 调用 API → 保存到缓存

预计命中率 30-50%，可节省大量 API 费用。
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ResponseCache:
    """AI 响应缓存（线程安全）"""

    def __init__(self, cache_dir: str = None, ttl_seconds: int = 3600):
        """
        Args:
            cache_dir: 缓存数据库存放目录，默认 data/ai_cache/
            ttl_seconds: 缓存过期时间（秒），默认 3600（1小时）
        """
        if cache_dir is None:
            # Docker 环境：使用挂载卷 /app/output/ 确保缓存持久化
            docker_output = Path("/app/output")
            if docker_output.exists():
                cache_dir = docker_output / "ai_cache"
            else:
                # 本地环境：相对于项目根目录
                base = Path(__file__).resolve().parent.parent.parent.parent  # TrendRadar/
                cache_dir = base / "data" / "ai_cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.cache_dir / "response_cache.db"
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        self._init_db()

        # 统计
        self.hits = 0
        self.misses = 0

    def _init_db(self):
        """初始化缓存数据库"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS response_cache (
                    cache_key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    model TEXT NOT NULL,
                    messages_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at
                ON response_cache(expires_at)
            """)
            conn.commit()
            conn.close()

    def _make_key(self, messages: List[Dict[str, str]], model: str, temperature: float = None) -> str:
        """生成缓存键（SHA256）"""
        raw = json.dumps({
            "messages": messages,
            "model": model,
            "temperature": temperature,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, messages: List[Dict[str, str]], model: str, temperature: float = None) -> Optional[str]:
        """
        查询缓存。

        Returns:
            缓存的响应内容，若未命中或已过期则返回 None
        """
        key = self._make_key(messages, model, temperature)
        now = time.time()

        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            row = conn.execute(
                "SELECT response, expires_at, hit_count FROM response_cache WHERE cache_key = ?",
                (key,)
            ).fetchone()

            if row is None:
                self.misses += 1
                conn.close()
                return None

            response, expires_at, hit_count = row

            if now > expires_at:
                # 缓存已过期
                conn.execute("DELETE FROM response_cache WHERE cache_key = ?", (key,))
                conn.commit()
                self.misses += 1
                conn.close()
                return None

            # 缓存命中，更新命中次数
            conn.execute(
                "UPDATE response_cache SET hit_count = ? WHERE cache_key = ?",
                (hit_count + 1, key)
            )
            conn.commit()
            conn.close()

            self.hits += 1
            return response

    def set(self, messages: List[Dict[str, str]], response: str, model: str, temperature: float = None):
        """保存响应到缓存"""
        key = self._make_key(messages, model, temperature)
        now = time.time()
        messages_hash = hashlib.sha256(
            json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]

        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                INSERT OR REPLACE INTO response_cache
                (cache_key, response, model, messages_hash, created_at, expires_at, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (key, response, model, messages_hash, now, now + self.ttl))
            conn.commit()
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = self.hits + self.misses
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            total_entries = conn.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
            expired_count = conn.execute(
                "SELECT COUNT(*) FROM response_cache WHERE expires_at < ?",
                (time.time(),)
            ).fetchone()[0]
            conn.close()

        return {
            "total_entries": total_entries,
            "expired_entries": expired_count,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total * 100, 1) if total > 0 else 0,
            "total_requests": total,
            "cache_db_path": str(self.db_path),
        }

    def clear_expired(self) -> int:
        """清理过期缓存，返回清理条数"""
        now = time.time()
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            count = conn.execute(
                "DELETE FROM response_cache WHERE expires_at < ?", (now,)
            ).rowcount
            conn.commit()
            conn.close()
        return count

    def clear_all(self):
        """清空全部缓存"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("DELETE FROM response_cache")
            conn.commit()
            conn.close()


# 全局单例
_cache_instance = None
_cache_lock = threading.Lock()


def get_cache(cache_dir: str = None, ttl_seconds: int = 3600) -> ResponseCache:
    """获取全局缓存单例"""
    global _cache_instance
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                _cache_instance = ResponseCache(cache_dir, ttl_seconds)
    return _cache_instance


def cached_chat(client, messages: List[Dict[str, str]], **kwargs) -> str:
    """
    带缓存的 AI 对话调用。

    用法:
        from trendradar.ai.response_cache import cached_chat
        response = cached_chat(client, messages)
    """
    cache = get_cache()
    model = client.model
    temperature = kwargs.get("temperature", client.temperature)

    # 查询缓存
    cached = cache.get(messages, model, temperature)
    if cached is not None:
        return cached

    # 缓存 miss → 调用 API
    response = client.chat(messages, **kwargs)

    # 保存到缓存（非空响应才缓存）
    if response and response.strip():
        cache.set(messages, response, model, temperature)

    return response
