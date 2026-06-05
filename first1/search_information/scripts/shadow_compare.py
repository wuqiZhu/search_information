# -*- coding: utf-8 -*-
"""
影子模式对比脚本 — LoRA vs DeepSeek 质量验证

比较百器模型第2层（LoRA）和第3层（DeepSeek）对同一批新闻的输出一致性。

用法:
    # 用当天新闻对比（默认）
    python3 shadow_compare.py

    # 指定日期和条数
    python3 shadow_compare.py --date 2026-06-05 --limit 30

    # 只跑 LoRA（不调 DeepSeek，省 API 费用）
    python3 shadow_compare.py --lora-only

    # 输出 JSON 结果
    python3 shadow_compare.py --json
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ── 配置 ──
LORA_API = "http://8.140.232.52:5075"
DEFAULT_LIMIT = 20  # 默认对比条数
DB_BASE = "/app/output/news"  # 容器内数据库路径（Docker）
LOCAL_DB_BASE = "/root/projects/data/search_information/news"  # 宿主机 DB 路径


def get_news(date: str, limit: int = DEFAULT_LIMIT) -> list:
    """从数据库取新闻"""
    # 尝试容器路径，再试宿主机路径
    for base in [DB_BASE, LOCAL_DB_BASE]:
        db_path = Path(base) / f"{date}.db"
        if db_path.exists():
            break
    else:
        print(f"❌ 未找到 {date}.db（尝试过: {DB_BASE} 和 {LOCAL_DB_BASE}）")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        """SELECT title, platform_id, url FROM news_items
           WHERE title IS NOT NULL AND title != ''
           ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"title": r[0], "platform": r[1], "url": r[2]} for r in rows]


def call_lora(task: str, data: dict) -> dict:
    """调用阿里云 LoRA 服务"""
    body = json.dumps({"task": task, "data": data}).encode()
    req = urllib.request.Request(
        f"{LORA_API}/infer",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return resp.get("result", {})
    except Exception as e:
        return {"error": str(e)}


def call_deepseek(title: str, platform: str) -> dict:
    """调用 DeepSeek（通过小米 API）做相关性和紧急度判断"""
    from trendradar.ai.client import AIClient
    from trendradar.core.loader import load_config

    cfg = load_config()
    client = AIClient(cfg.get("AI", {}))

    prompt = f"""分析以下新闻的投资相关性和紧急程度，只输出 JSON：

新闻: {title}
平台: {platform}

{{
  "relevance_score": <0-10>,
  "urgency": "high|medium|low",
  "reason": "<一句话原因>"
}}"""
    try:
        resp = client.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,
        )
        # 提取 JSON
        start = resp.find("{")
        end = resp.rfind("}")
        if start >= 0 and end > start:
            return json.loads(resp[start : end + 1])
        return {"error": "未找到 JSON", "raw": resp[:200]}
    except Exception as e:
        return {"error": str(e)}


def print_comparison(news_list: list, lora_only: bool = False):
    """执行对比并打印结果"""
    results = []

    print(f"\n{'='*70}")
    print(f"影子模式对比 — LoRA vs {'DeepSeek' if not lora_only else '（仅LoRA）'}")
    print(f"{'='*70}")
    print(f"共 {len(news_list)} 条新闻\n")

    lora_scores = []

    for i, item in enumerate(news_list):
        title = item["title"][:60]
        platform = item["platform"]

        # LoRA 相关评分
        lora_r = call_lora("relevance_score", {
            "title": item["title"],
            "summary": "",
            "category": "综合",
        })
        lora_score = lora_r.get("score", -1)
        if lora_score >= 0:
            lora_scores.append(lora_score)

        # LoRA 紧急度
        lora_u = call_lora("urgency", {
            "title": item["title"],
            "platform": platform,
            "rank_change": "",
        })
        lora_urgency = lora_u.get("level", "?")

        # DeepSeek
        ds = {}
        if not lora_only:
            ds = call_deepseek(item["title"], platform)

        record = {
            "title": item["title"][:60],
            "platform": platform,
            "lora_score": lora_score,
            "lora_urgency": lora_urgency,
            "ds_score": ds.get("relevance_score", -1),
            "ds_urgency": ds.get("urgency", "?"),
            "ds_reason": ds.get("reason", ""),
        }
        results.append(record)

        # 打印
        score_match = "✅" if not lora_only and abs(lora_score - ds.get("relevance_score", -1)) <= 2 else " "
        urgency_match = "✅" if not lora_only and lora_urgency == ds.get("urgency", "") else " "

        print(f"  [{i+1}] {title}")
        print(f"       LoRA  : 相关={lora_score} {score_match} | 紧急={lora_urgency} {urgency_match}")
        if not lora_only:
            ds_s = ds.get("relevance_score", "?")
            ds_u = ds.get("urgency", "?")
            ds_r = ds.get("reason", "")[:40]
            print(f"       DeepSeek: 相关={ds_s} | 紧急={ds_u} | {ds_r}")
        print()

    # ── 统计摘要 ──
    print(f"{'='*70}")
    print("📊 统计摘要")
    print(f"{'='*70}")

    if lora_scores:
        avg = sum(lora_scores) / len(lora_scores)
        high = sum(1 for s in lora_scores if s >= 7)
        mid = sum(1 for s in lora_scores if 4 <= s < 7)
        low = sum(1 for s in lora_scores if s < 4)
        print(f"LoRA 相关评分:")
        print(f"  平均: {avg:.1f} | 高相关(>=7): {high}条 | 中相关(4-6): {mid}条 | 低相关(<4): {low}条")

    if not lora_only:
        ds_scores = [r["ds_score"] for r in results if r["ds_score"] >= 0]
        if ds_scores:
            ds_avg = sum(ds_scores) / len(ds_scores)
            print(f"DeepSeek 相关评分:")
            print(f"  平均: {ds_avg:.1f}")

            # 一致性
            matched = 0
            total = 0
            urgency_matched = 0
            for r in results:
                if r["lora_score"] >= 0 and r["ds_score"] >= 0:
                    total += 1
                    if abs(r["lora_score"] - r["ds_score"]) <= 2:
                        matched += 1
                if r["lora_urgency"] != "?" and r["ds_urgency"] != "?":
                    if r["lora_urgency"] == r["ds_urgency"]:
                        urgency_matched += 1

            if total > 0:
                print(f"\n🎯 一致性:")
                print(f"  相关评分 (±2): {matched}/{total} = {matched/total*100:.0f}%")
            if urgency_matched > 0:
                print(f"  紧急度判断:   {urgency_matched}/{total} = {urgency_matched/total*100:.0f}%")

    return results


def main():
    parser = argparse.ArgumentParser(description="影子模式对比 — LoRA vs DeepSeek")
    parser.add_argument("--date", type=str, default=None, help="日期 (YYYY-MM-DD)，默认今天")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="对比条数")
    parser.add_argument("--lora-only", action="store_true", help="仅跑 LoRA，不调 DeepSeek")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    args = parser.parse_args()

    date = args.date or datetime.now().strftime("%Y-%m-%d")
    news = get_news(date, args.limit)

    if not news:
        print(f"❌ {date} 没有新闻数据")
        sys.exit(1)

    print(f"取到 {len(news)} 条新闻")

    results = print_comparison(news, args.lora_only)

    if args.json:
        print("\n=== JSON 输出 ===")
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
