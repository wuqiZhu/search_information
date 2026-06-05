#!/usr/bin/env python3
"""
自动信号生成 — 从每日新闻DB匹配金字塔关键词，自动推入 signal_tracker

运行方式:
  python3 auto_signals.py                    # 处理今日新闻
  python3 auto_signals.py --date 2026-06-03  # 指定日期
  python3 auto_signals.py --cron             # 静默模式（cron用）

安装为cron（每2小时）:
  0 */2 * * * cd /root/projects/scripts && python3 auto_signals.py --cron >> /var/log/auto_signals.log 2>&1
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, "/root/projects/invest/scripts")
from signal_tracker import get_tracker, add_signal


def load_keywords(kw_path):
    """解析 frequency_words.txt 返回 {group: {keywords:[], level:str}}

    处理格式:
      - 单行: 央行, rate cut, 公积金
      - 正则: /\\bFed\\b/, /宽松|紧缩/ => 货币政策
      - 管线和: 人民币|CNY|RMB
    """
    groups = {}
    current = None

    def extract_kw(line):
        """从一行提取关键词"""
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        # 正则格式: /pattern/ 或 /pattern/ => mapping
        if line.startswith("/"):
            m = re.match(r"/([^/]+)/", line)
            if m:
                return m.group(1)
            return None
        # 跳过 => 映射
        if " => " in line:
            return None
        # 关键字包含 | 管道符
        if "|" in line:
            return line
        # 单行关键字
        if len(line) >= 2 and not line.startswith("\\"):
            return line
        return None

    with open(kw_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and "] " in line:
                name = line.split("]")[0].lstrip("[").strip()
                current = name
                groups[current] = {"keywords": [], "level": "⚪"}
                if "⭐" in line:
                    groups[current]["level"] = "🔴"
                elif "📁" in line:
                    groups[current]["level"] = "🟡"
            elif current:
                kw = extract_kw(line)
                if kw:
                    # 管道符格式: 拆成多个关键词
                    if "|" in kw:
                        for part in kw.split("|"):
                            part = part.strip()
                            if len(part) >= 2:
                                groups[current]["keywords"].append(part)
                    else:
                        groups[current]["keywords"].append(kw)
    return groups


def load_titles_from_db(db_path, silent=False):
    """从SQLite加载标题列表"""
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        titles = [row[0] for row in conn.execute("SELECT title FROM news_items").fetchall()]
        conn.close()
        if not silent:
            print("  %s: %d titles" % (db_path, len(titles)))
        return titles
    except Exception as e:
        if not silent:
            print("  %s: error - %s" % (db_path, e))
        return []


def match_keywords(titles, kw_groups, silent=False):
    """匹配关键词，返回 {group: {hits, level, samples}}"""
    topic_hits = {}
    for group_name, group_data in kw_groups.items():
        hits = 0
        hit_titles = []
        for kw in group_data["keywords"]:
            if len(kw) < 2:
                continue
            try:
                if "\\b" in kw or "\\B" in kw:
                    pat = re.compile(kw, re.IGNORECASE | re.UNICODE)
                else:
                    pat = re.compile(re.escape(kw), re.IGNORECASE | re.UNICODE)
            except re.error:
                continue
            for t in titles:
                if pat.search(t):
                    hits += 1
                    if len(hit_titles) < 3:
                        hit_titles.append(t[:80])
                    break
        if hits > 0:
            topic_hits[group_name] = {"hits": hits, "level": group_data["level"], "samples": hit_titles}
    return topic_hits


def process_date(date_str, silent=False):
    """处理指定日期的新闻和RSS，生成信号"""
    kw_path = "/root/projects/search_information/search_information/TrendRadar/config/frequency_words.txt"
    kw_groups = load_keywords(kw_path)
    if not silent:
        print("Loaded %d keyword groups" % len(kw_groups))

    # 加载热榜新闻标题
    news_db = "/root/projects/data/search_information/news/%s.db" % date_str
    news_titles = load_titles_from_db(news_db, silent)
    # 加载RSS标题
    rss_db = "/root/projects/data/search_information/rss/%s.db" % date_str
    rss_titles = load_titles_from_db(rss_db, silent)

    all_titles = news_titles + rss_titles
    if not all_titles:
        if not silent:
            print("No data for %s" % date_str)
        return 0

    # 匹配
    news_hits = match_keywords(news_titles, kw_groups, silent)
    rss_hits = match_keywords(rss_titles, kw_groups, silent)
    # 合并: 取并集，hits相加，samples取热榜优先
    merged = {}
    all_groups = set(list(news_hits.keys()) + list(rss_hits.keys()))
    for g in all_groups:
        n = news_hits.get(g, {})
        r = rss_hits.get(g, {})
        merged[g] = {
            "hits": n.get("hits", 0) + r.get("hits", 0),
            "level": n.get("level") or r.get("level") or "⚪",
            "samples": n.get("samples", [])[:2] + r.get("samples", [])[:1],
        }

    sorted_topics = sorted(merged.items(), key=lambda x: -x[1]["hits"])

    if not silent:
        print("\n=== Top话题 ===")
        for name, data in sorted_topics[:15]:
            print("  %s %s: %d hits" % (data["level"], name, data["hits"]))

    # 推入 signal_tracker
    st = get_tracker()
    added = 0
    for name, data in sorted_topics:
        if data["level"] == "🔴":
            threshold = 1
        elif data["level"] == "🟡":
            threshold = 3
        else:
            threshold = 5
        if data["hits"] >= threshold:
            sample = data["samples"][0] if data["samples"] else name
            add_signal(name, "新闻", sample[:80], data["level"],
                       source_url="", related_data={"hits": data["hits"], "date": date_str})
            added += 1

    if not silent:
        print("\nAdded %d signals, total topics: %d" % (added, len(st.get_all_topics())))
    return added


def main():
    import argparse
    parser = argparse.ArgumentParser(description="自动信号生成")
    parser.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--cron", action="store_true", help="静默模式")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    silent = args.cron
    added = process_date(date_str, silent)
    if not silent:
        print("Done. Added %d signals." % added)


if __name__ == "__main__":
    main()
