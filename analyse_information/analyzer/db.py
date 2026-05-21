import sqlite3
import hashlib
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "./shared/data/analyzer.db"
_db_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    with _db_lock:
        conn = get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                url_hash TEXT NOT NULL UNIQUE,
                title TEXT,
                status TEXT NOT NULL,
                score REAL,
                category TEXT,
                reason TEXT,
                obsidian_path TEXT,
                feedback TEXT DEFAULT '',
                translation_cache TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_url_hash ON processed_urls(url_hash);
            CREATE INDEX IF NOT EXISTS idx_status ON processed_urls(status);
            CREATE INDEX IF NOT EXISTS idx_category ON processed_urls(category);
            CREATE INDEX IF NOT EXISTS idx_created_at ON processed_urls(created_at);
            CREATE INDEX IF NOT EXISTS idx_feedback ON processed_urls(feedback);
        """)

        try:
            conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                    title, reason, translation_cache,
                    content='processed_urls',
                    content_rowid='id'
                );

                CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON processed_urls BEGIN
                    INSERT INTO articles_fts(rowid, title, reason, translation_cache)
                    VALUES (new.id, new.title, new.reason, new.translation_cache);
                END;

                CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON processed_urls BEGIN
                    INSERT INTO articles_fts(articles_fts, rowid, title, reason, translation_cache)
                    VALUES ('delete', old.id, old.title, old.reason, old.translation_cache);
                END;

                CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON processed_urls BEGIN
                    INSERT INTO articles_fts(articles_fts, rowid, title, reason, translation_cache)
                    VALUES ('delete', old.id, old.title, old.reason, old.translation_cache);
                    INSERT INTO articles_fts(rowid, title, reason, translation_cache)
                    VALUES (new.id, new.title, new.reason, new.translation_cache);
                END;
            """)
        except Exception as e:
            logger.warning("FTS5 触发器创建跳过 (可能已存在): %s", e)

        conn.commit()
        conn.close()
    logger.info("数据库初始化完成: %s", DB_PATH)


def _url_hash(url: str) -> str:
    return hashlib.md5(url.strip().encode("utf-8")).hexdigest()


def is_url_processed(url: str) -> bool:
    with _db_lock:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT id FROM processed_urls WHERE url_hash = ?",
                (_url_hash(url),),
            ).fetchone()
            return row is not None
        finally:
            conn.close()


def get_url_record(url: str) -> Optional[dict]:
    with _db_lock:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM processed_urls WHERE url_hash = ?",
                (_url_hash(url),),
            ).fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()


def save_result(url: str, result: dict):
    with _db_lock:
        conn = get_connection()
        try:
            now = datetime.now().isoformat()
            h = _url_hash(url)
            existing = conn.execute(
                "SELECT id FROM processed_urls WHERE url_hash = ?", (h,)
            ).fetchone()

            translation_cache = result.get("translation", "")[:5000]

            if existing:
                conn.execute("""
                    UPDATE processed_urls
                    SET title=?, status=?, score=?, category=?, reason=?, obsidian_path=?, translation_cache=?, updated_at=?
                    WHERE url_hash=?
                """, (
                    result.get("title", ""),
                    result.get("status", "unknown"),
                    result.get("score"),
                    result.get("category", ""),
                    result.get("reason", ""),
                    result.get("obsidian_path", ""),
                    translation_cache,
                    now,
                    h,
                ))
            else:
                conn.execute("""
                    INSERT INTO processed_urls (url, url_hash, title, status, score, category, reason, obsidian_path, translation_cache, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    url,
                    h,
                    result.get("title", ""),
                    result.get("status", "unknown"),
                    result.get("score"),
                    result.get("category", ""),
                    result.get("reason", ""),
                    result.get("obsidian_path", ""),
                    translation_cache,
                    now,
                    now,
                ))
            conn.commit()
        finally:
            conn.close()


def search_articles(query: str, limit: int = 10) -> list:
    with _db_lock:
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT p.id, p.url, p.title, p.status, p.score, p.category,
                       p.reason, p.obsidian_path, p.feedback, p.created_at,
                       highlight(articles_fts, 0, '>>>', '<<<') as title_hl
                FROM articles_fts
                JOIN processed_urls p ON articles_fts.rowid = p.id
                WHERE articles_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, limit)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            rows = conn.execute("""
                SELECT id, url, title, status, score, category, reason,
                       obsidian_path, feedback, created_at
                FROM processed_urls
                WHERE title LIKE ? OR reason LIKE ? OR translation_cache LIKE ?
                ORDER BY score DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def set_feedback(url: str, feedback: str) -> bool:
    with _db_lock:
        conn = get_connection()
        try:
            h = _url_hash(url)
            now = datetime.now().isoformat()
            cursor = conn.execute(
                "UPDATE processed_urls SET feedback=?, updated_at=? WHERE url_hash=?",
                (feedback, now, h),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def get_feedback_stats() -> dict:
    with _db_lock:
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT feedback, COUNT(*) as cnt
                FROM processed_urls
                WHERE feedback != '' AND feedback IS NOT NULL
                GROUP BY feedback
            """).fetchall()
            return {row["feedback"]: row["cnt"] for row in rows}
        finally:
            conn.close()


def get_user_preferences() -> dict:
    with _db_lock:
        conn = get_connection()
        try:
            liked = conn.execute("""
                SELECT category, title, reason FROM processed_urls
                WHERE feedback='useful' AND status='success'
                ORDER BY created_at DESC LIMIT 20
            """).fetchall()

            disliked = conn.execute("""
                SELECT category, title, reason FROM processed_urls
                WHERE feedback='not_useful' AND status='success'
                ORDER BY created_at DESC LIMIT 20
            """).fetchall()

            top_categories = conn.execute("""
                SELECT category, COUNT(*) as cnt FROM processed_urls
                WHERE feedback='useful' AND category != ''
                GROUP BY category ORDER BY cnt DESC LIMIT 5
            """).fetchall()

            return {
                "liked": [dict(r) for r in liked],
                "disliked": [dict(r) for r in disliked],
                "top_categories": [dict(r) for r in top_categories],
            }
        finally:
            conn.close()


def get_stats() -> dict:
    with _db_lock:
        conn = get_connection()
        try:
            total = conn.execute("SELECT COUNT(*) FROM processed_urls").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM processed_urls WHERE status='success'").fetchone()[0]
            not_relevant = conn.execute("SELECT COUNT(*) FROM processed_urls WHERE status='not_relevant'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM processed_urls WHERE status IN ('extract_failed','error','ai_failed')").fetchone()[0]

            categories = conn.execute("""
                SELECT category, COUNT(*) as cnt
                FROM processed_urls
                WHERE status='success' AND category != ''
                GROUP BY category
                ORDER BY cnt DESC
            """).fetchall()

            recent = conn.execute("""
                SELECT url, title, status, score, category, feedback, created_at
                FROM processed_urls
                ORDER BY created_at DESC
                LIMIT 10
            """).fetchall()

            return {
                "total": total,
                "success": success,
                "not_relevant": not_relevant,
                "failed": failed,
                "categories": {row["category"]: row["cnt"] for row in categories},
                "recent": [dict(r) for r in recent],
            }
        finally:
            conn.close()
