import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_daily_digest(db_path: str = "./shared/data/analyzer.db", output_dir: str = "./knowledge_base/obsidian") -> str:
    import sqlite3
    import json

    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT url, title, status, score, category, reason, obsidian_path, created_at
        FROM processed_urls
        WHERE date(created_at) >= ? AND status IN ('success', 'not_relevant')
        ORDER BY score DESC
    """, (yesterday,)).fetchall()
    conn.close()

    if not rows:
        logger.info("今日无新文章，跳过摘要生成")
        return ""

    articles = [dict(r) for r in rows]
    success = [a for a in articles if a["status"] == "success"]
    not_relevant = [a for a in articles if a["status"] == "not_relevant"]

    lines = [
        "---",
        f'title: "每日摘要 {today}"',
        f"date: {today}",
        "type: digest",
        "tags: [digest, daily-summary]",
        "---",
        "",
        f"# 每日摘要 {today}",
        "",
        f"今日共处理 **{len(articles)}** 篇文章，其中 **{len(success)}** 篇成功沉淀，**{len(not_relevant)}** 篇被过滤。",
        "",
    ]

    if success:
        lines.append("## 今日精选\n")
        for i, a in enumerate(success, 1):
            score = a.get("score", 0)
            category = a.get("category", "")
            title = a.get("title", "")
            url = a.get("url", "")
            reason = a.get("reason", "")
            obsidian_path = a.get("obsidian_path", "")

            star = "⭐" if score >= 8 else ""
            lines.append(f"### {i}. {star} {title}")
            lines.append(f"- **评分**: {score:.1f}/10 | **分类**: {category}")
            lines.append(f"- **摘要**: {reason}")
            lines.append(f"- **原文**: [{url}]({url})")
            if obsidian_path:
                filename = Path(obsidian_path).stem
                lines.append(f"- **笔记**: [[{filename}]]")
            lines.append("")

    category_counts = {}
    for a in success:
        cat = a.get("category", "未分类")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    if category_counts:
        lines.append("## 分类统计\n")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}: {count} 篇")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    digest_content = "\n".join(lines)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filepath = output_path / f"00-收件箱" / f"{today}_每日摘要.md"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(digest_content, encoding="utf-8")
    logger.info("每日摘要已生成: %s", filepath)

    return str(filepath)


def generate_weekly_digest(db_path: str = "./shared/data/analyzer.db", output_dir: str = "./knowledge_base/obsidian") -> str:
    import sqlite3

    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row

    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    week_start_str = week_start.strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT url, title, status, score, category, reason, obsidian_path, created_at
        FROM processed_urls
        WHERE date(created_at) >= ? AND status = 'success'
        ORDER BY score DESC
    """, (week_start_str,)).fetchall()
    conn.close()

    if not rows:
        logger.info("本周无成功沉淀的文章，跳过摘要生成")
        return ""

    articles = [dict(r) for r in rows]
    week_end = today.strftime("%Y-%m-%d")

    lines = [
        "---",
        f'title: "每周摘要 {week_start_str} ~ {week_end}"',
        f"date: {week_end}",
        "type: weekly-digest",
        "tags: [digest, weekly-summary]",
        "---",
        "",
        f"# 每周摘要 {week_start_str} ~ {week_end}",
        "",
        f"本周共成功沉淀 **{len(articles)}** 篇文章。",
        "",
        "## Top 10 精选\n",
    ]

    for i, a in enumerate(articles[:10], 1):
        score = a.get("score", 0)
        category = a.get("category", "")
        title = a.get("title", "")
        obsidian_path = a.get("obsidian_path", "")
        lines.append(f"{i}. **[{score:.1f}]** [{category}] {title}")
        if obsidian_path:
            filename = Path(obsidian_path).stem
            lines.append(f"   [[{filename}]]")
        lines.append("")

    category_counts = {}
    for a in articles:
        cat = a.get("category", "未分类")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    if category_counts:
        lines.append("## 分类分布\n")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            bar = "█" * count
            lines.append(f"- {cat}: {bar} ({count})")
        lines.append("")

    avg_score = sum(a.get("score", 0) for a in articles) / len(articles) if articles else 0
    max_score = max(a.get("score", 0) for a in articles) if articles else 0

    lines.append("## 统计数据\n")
    lines.append(f"- 平均评分: {avg_score:.1f}")
    lines.append(f"- 最高评分: {max_score:.1f}")
    lines.append(f"- 文章总数: {len(articles)}")
    lines.append("")
    lines.append("---")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    digest_content = "\n".join(lines)

    output_path = Path(output_dir)
    filepath = output_path / "00-收件箱" / f"{week_end}_每周摘要.md"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(digest_content, encoding="utf-8")
    logger.info("每周摘要已生成: %s", filepath)

    return str(filepath)
