import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

NOTE_TEMPLATE = """---
title: "{title}"
source: "{url}"
date: {date}
category: "{category}"
score: {score}
tags: [{tags}]
---

# {title}

## 一句话总结

{summary}

## 大白话翻译

{translation}

## 原始信息

- **来源**: [{url}]({url})
- **采集时间**: {date}
- **相关性评分**: {score}/10
- **分类**: {category}

## 关键要点

{key_points}

{related_section}

---

> 本文由「信息分析与知识沉淀」流水线自动生成
"""


class KnowledgeBuilder:
    def __init__(self, config: dict):
        self.obsidian_path = Path(config.get("obsidian_path", "./knowledge_base/obsidian"))
        self.analyzed_path = Path(config.get("analyzed_path", "./knowledge_base/analyzed"))
        self.translated_path = Path(config.get("translated_path", "./knowledge_base/translated"))
        self.inbox_path = self.obsidian_path / "00-收件箱"

    def build_note(self, data: dict, related_notes: list = None) -> str:
        title = data.get("title", "Unknown")
        url = data.get("url", "")
        category = data.get("category", "00-收件箱")
        score = data.get("score", 0)
        translation = data.get("translation", "")
        tags = self._extract_tags(data)

        summary = self._extract_summary(translation)
        key_points = self._extract_key_points(translation)
        related_section = self._build_related_section(related_notes)

        note = NOTE_TEMPLATE.format(
            title=title.replace('"', '\\"'),
            url=url,
            date=datetime.now().strftime("%Y-%m-%d"),
            category=category,
            score=score,
            tags=", ".join([f'"{t}"' for t in tags]),
            summary=summary,
            translation=translation,
            key_points=key_points,
            related_section=related_section,
        )
        return note

    def save_to_obsidian(self, data: dict, related_notes: list = None) -> str:
        note_content = self.build_note(data, related_notes)
        category = data.get("category", "00-收件箱")
        title = data.get("title", "unknown")
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:60]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{safe_name}.md"

        if category and category != "00-收件箱":
            category_dir = self.obsidian_path / category
        else:
            category_dir = self.inbox_path

        category_dir.mkdir(parents=True, exist_ok=True)
        filepath = category_dir / filename

        counter = 1
        while filepath.exists():
            filename = f"{ts}_{counter}_{safe_name}.md"
            filepath = category_dir / filename
            counter += 1

        filepath.write_text(note_content, encoding="utf-8")
        logger.info("Obsidian 笔记已保存: %s", filepath)
        return str(filepath)

    def save_analyzed(self, data: dict) -> str:
        """保存分析结果到 analyzed 目录"""
        self.analyzed_path.mkdir(parents=True, exist_ok=True)
        title = data.get("title", "unknown")
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:60]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{safe_name}.json"
        filepath = self.analyzed_path / filename

        import json
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("分析结果已保存: %s", filepath)
        return str(filepath)

    def save_translated(self, data: dict) -> str:
        """保存翻译结果到 translated 目录"""
        self.translated_path.mkdir(parents=True, exist_ok=True)
        title = data.get("title", "unknown")
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:60]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{safe_name}.md"
        filepath = self.translated_path / filename

        md = f"""# {data.get('title', 'Unknown')}

- **来源**: {data.get('url', '')}
- **翻译时间**: {datetime.now().isoformat()}
- **相关性评分**: {data.get('score', 0)}/10

---

{data.get('translation', '')}
"""
        filepath.write_text(md, encoding="utf-8")
        logger.info("翻译结果已保存: %s", filepath)
        return str(filepath)

    def _build_related_section(self, related_notes: list = None) -> str:
        if not related_notes:
            return ""
        lines = ["## 相关笔记\n"]
        for note in related_notes[:5]:
            title = note.get("title", "")
            score = note.get("score", 0)
            category = note.get("category", "")
            obsidian_path = note.get("obsidian_path", "")
            if obsidian_path:
                filename = Path(obsidian_path).stem
                lines.append(f"- [[{filename}]] ({category}, 评分: {score:.1f})")
            else:
                lines.append(f"- {title} ({category}, 评分: {score:.1f})")
        return "\n".join(lines)

    def _extract_tags(self, data: dict) -> list:
        """从分析结果中提取标签"""
        tags = ["auto-analyzed"]
        category = data.get("category", "")
        if category:
            cat_name = category.split("-", 1)[-1] if "-" in category else category
            tags.append(cat_name)
        return tags

    def _extract_summary(self, translation: str) -> str:
        """从翻译结果中提取一句话总结"""
        lines = translation.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-") and len(line) > 10:
                return line[:200]
        return "暂无总结"

    def _extract_key_points(self, translation: str) -> str:
        """从翻译结果中提取关键要点"""
        lines = translation.strip().split("\n")
        points = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* ") or stripped.startswith("1. "):
                in_list = True
                points.append(stripped)
            elif in_list and not stripped:
                break
        if points:
            return "\n".join(points[:5])
        return "- 请查看大白话翻译部分"
