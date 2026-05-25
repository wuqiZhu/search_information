"""数据库模块测试"""
import os
import pytest
from unittest.mock import patch


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_analyzer.db")
    with patch('analyzer.db.DB_PATH', db_path):
        from analyzer.db import init_db
        init_db()
        yield db_path


def test_init_db(temp_db):
    import sqlite3
    conn = sqlite3.connect(temp_db)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    assert 'processed_urls' in table_names
    conn.close()


def test_save_and_check_url(temp_db):
    from analyzer.db import save_result, is_url_processed
    url = "https://example.com/article1"
    assert is_url_processed(url) is False
    save_result(url, {"status": "success", "title": "测试文章", "score": 8.5, "category": "测试"})
    assert is_url_processed(url) is True


def test_get_url_record(temp_db):
    from analyzer.db import save_result, get_url_record
    url = "https://example.com/article2"
    save_result(url, {"status": "success", "title": "测试文章2", "score": 7.0, "category": "分类"})
    record = get_url_record(url)
    assert record is not None
    assert record["title"] == "测试文章2"
    assert record["score"] == 7.0


def test_get_url_record_not_found(temp_db):
    from analyzer.db import get_url_record
    record = get_url_record("https://nonexistent.com")
    assert record is None


def test_search_articles(temp_db):
    from analyzer.db import save_result, search_articles
    save_result("https://example.com/1", {"status": "success", "title": "embedded linux guide", "score": 9.0, "reason": "kernel development"})
    save_result("https://example.com/2", {"status": "success", "title": "python tutorial", "score": 3.0, "reason": "programming basics"})
    results = search_articles("embedded")
    assert len(results) >= 1


def test_set_feedback(temp_db):
    from analyzer.db import save_result, set_feedback, get_url_record
    url = "https://example.com/feedback"
    save_result(url, {"status": "success", "title": "反馈测试", "score": 8.0})
    success = set_feedback(url, "useful")
    assert success is True
    record = get_url_record(url)
    assert record["feedback"] == "useful"


def test_get_stats(temp_db):
    from analyzer.db import save_result, get_stats
    save_result("https://example.com/s1", {"status": "success", "title": "A", "score": 8.0, "category": "C1"})
    save_result("https://example.com/s2", {"status": "not_relevant", "title": "B", "score": 2.0})
    stats = get_stats()
    assert stats["total"] == 2
    assert stats["success"] == 1
    assert stats["not_relevant"] == 1