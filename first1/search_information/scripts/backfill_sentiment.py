#!/usr/bin/env python3
"""
回填情绪历史 — 从 news_sentiment 表按日聚合生成历史记录

在 Docker 环境运行:
  docker cp backfill_sentiment.py invest-backend:/app/scripts/
  docker exec invest-backend python /app/scripts/backfill_sentiment.py
"""
import json
import math
import os
import sqlite3
from datetime import datetime, timedelta

DB = "/root/projects/data/invest/fund_data.db"
HISTORY_FILE = "/root/projects/data/invest/sentiment/sentiment_history.json"

def load_existing():
    """加载已有历史"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def backfill():
    # 1. 连接数据库
    conn = sqlite3.connect(DB)

    # 2. 按日期聚合
    rows = conn.execute("""
        SELECT
            date,
            COUNT(*) as cnt,
            AVG(sentiment_score) as avg_score,
            SUM(COALESCE(positive_count,0)) as pos,
            SUM(COALESCE(negative_count,0)) as neg,
            SUM(COALESCE(neutral_count,0)) as neu
        FROM news_sentiment
        WHERE date IS NOT NULL
        GROUP BY date
        ORDER BY date
    """).fetchall()

    print(f"数据库中找到 {len(rows)} 天数据:")

    # 3. 构建新记录
    existing = load_existing()
    existing_dates = {h.get("date") for h in existing}
    print(f"已有历史: {len(existing)} 条, 日期: {sorted(existing_dates)}")

    new_records = []
    for date, cnt, avg_score, pos, neg, neu in rows:
        if date in existing_dates:
            print(f"  {date}: 已存在，跳过")
            continue

        # 将 avg_score (0~1) 映射到情绪指数 (0~100)
        index = round(avg_score * 100, 2) if avg_score else 50.0

        # 情绪等级
        if index >= 60:
            level = "贪婪"
        elif index >= 55:
            level = "偏贪婪"
        elif index >= 45:
            level = "中性"
        elif index >= 40:
            level = "偏恐惧"
        else:
            level = "恐惧"

        total = pos + neg + neu
        news_sentiment = avg_score if avg_score else 0.5
        market_momentum = 0.5  # 默认值，无回填数据
        volatility = 0.5
        technical_signals = 0.5
        social_sentiment = 0.5

        record = {
            "date": date,
            "index": index,
            "level": level,
            "components": {
                "news_sentiment": round(news_sentiment, 4),
                "market_momentum": market_momentum,
                "volatility": volatility,
                "technical_signals": technical_signals,
                "social_sentiment": social_sentiment
            },
            "timestamp": f"{date}T23:59:59"
        }
        new_records.append(record)
        print(f"  {date}: cnt={cnt} avg_score={avg_score} -> index={index} ({level})")

    if not new_records:
        print("\n无需回填，所有日期已存在")
        conn.close()
        return

    # 4. 合并并保存
    merged = existing + new_records
    merged.sort(key=lambda x: x["date"])
    merged = merged[-90:]  # 最多保留90天

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\n写入完成: 共 {len(merged)} 条记录 (新增 {len(new_records)} 条)")
    print(f"文件: {HISTORY_FILE}")

    # 5. 验证
    print("\n最终情绪历史:")
    for r in merged:
        print(f"  {r['date']}: {r['index']} ({r['level']})")

    conn.close()

if __name__ == "__main__":
    backfill()
