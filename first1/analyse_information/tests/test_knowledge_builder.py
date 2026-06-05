"""知识构建模块测试"""
import os
import pytest
from pathlib import Path


@pytest.fixture
def kb_config(tmp_path):
    return {
        "obsidian_path": str(tmp_path / "obsidian"),
        "analyzed_path": str(tmp_path / "analyzed"),
        "translated_path": str(tmp_path / "translated"),
    }


def test_build_note(kb_config):
    from analyzer.knowledge_builder import KnowledgeBuilder
    kb = KnowledgeBuilder(kb_config)
    data = {
        "title": "测试文章",
        "url": "https://example.com",
        "category": "06-嵌入式Linux",
        "score": 8.5,
        "translation": "这是一篇关于嵌入式Linux的文章\n- 要点1\n- 要点2",
        "difficulty": "中级",
        "action": "推荐阅读",
    }
    note = kb.build_note(data)
    assert "测试文章" in note
    assert "06-嵌入式Linux" in note
    assert "8.5" in note
    assert "推荐阅读" in note


def test_build_note_with_related(kb_config):
    from analyzer.knowledge_builder import KnowledgeBuilder
    kb = KnowledgeBuilder(kb_config)
    data = {
        "title": "测试文章",
        "url": "https://example.com",
        "category": "06-嵌入式Linux",
        "score": 8.5,
        "translation": "翻译内容",
        "difficulty": "中级",
        "action": "推荐阅读",
    }
    related = [{"title": "相关文章", "score": 7.0, "category": "06-嵌入式Linux", "obsidian_path": "/path/to/note"}]
    note = kb.build_note(data, related)
    assert "相关笔记" in note


def test_save_to_obsidian(kb_config):
    from analyzer.knowledge_builder import KnowledgeBuilder
    kb = KnowledgeBuilder(kb_config)
    data = {
        "title": "Obsidian测试",
        "url": "https://example.com/obsidian",
        "category": "06-嵌入式Linux",
        "score": 7.5,
        "translation": "翻译内容",
        "difficulty": "入门",
        "action": "可选阅读",
    }
    path = kb.save_to_obsidian(data)
    assert os.path.exists(path)
    content = Path(path).read_text(encoding="utf-8")
    assert "Obsidian测试" in content


def test_save_analyzed(kb_config):
    from analyzer.knowledge_builder import KnowledgeBuilder
    import json
    kb = KnowledgeBuilder(kb_config)
    data = {"title": "分析测试", "score": 8.0}
    path = kb.save_analyzed(data)
    assert os.path.exists(path)
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    assert content["title"] == "分析测试"