#!/usr/bin/env python3
"""
自动图表生成 - 情绪趋势、新闻量、基金净值

用法:
  python3 charts.py                      # 生成全部图表
  python3 charts.py --sentiment          # 情绪趋势图
  python3 charts.py --news               # 新闻量图
  python3 charts.py --output /tmp/charts # 指定输出目录

输出: PNG 图片, 存放在 audio_briefings/charts/
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 无头模式
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

plt.rcParams["font.sans-serif"] = ["Noto Serif CJK SC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

CHART_DIR = Path("/root/projects/data/search_information/audio_briefings/charts")
os.makedirs(CHART_DIR, exist_ok=True)


def chart_sentiment(output_dir: str):
    """情绪指数趋势图（近30天）"""
    hist_path = "/root/projects/data/invest/sentiment/sentiment_history.json"
    if not os.path.exists(hist_path):
        print("  ⚠️ 无情绪历史数据")
        return None

    with open(hist_path, "r") as f:
        hist = json.load(f)

    if not hist:
        return None

    dates = []
    values = []
    for h in hist[-30:]:
        dates.append(h.get("date", ""))
        values.append(h.get("index", 50))

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    colors = ["#f87171" if v > 60 else "#fbbf24" if v > 40 else "#4ade80" for v in values]
    bars = ax.bar(range(len(values)), values, color=colors, width=0.6, alpha=0.8)

    # 趋势线
    ax.plot(range(len(values)), values, color="#60a5fa", linewidth=2, alpha=0.6, marker="o", markersize=4)

    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels([d[-5:] if d else "" for d in dates], rotation=45, ha="right",
                       fontsize=9, color="#8888aa")
    ax.set_ylim(0, 100)
    ax.set_ylabel("指数", color="#8888aa")
    ax.tick_params(colors="#8888aa")

    # 阈值线
    ax.axhline(y=60, color="#f87171", linestyle="--", alpha=0.3, linewidth=1)
    ax.axhline(y=40, color="#4ade80", linestyle="--", alpha=0.3, linewidth=1)

    for spine in ax.spines.values():
        spine.set_color("#2a2a4a")

    ax.set_title("情绪指数趋势", color="#e0e0e0", fontsize=14, pad=15)

    path = os.path.join(output_dir, "sentiment_trend.png")
    plt.tight_layout()
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"  ✅ 情绪趋势图: {path} ({os.path.getsize(path)/1024:.0f} KB)")
    return path


def chart_news_volume(output_dir: str):
    """新闻量柱状图（近7天）"""
    news_dir = "/root/projects/data/search_information/news"
    if not os.path.exists(news_dir):
        print("  ⚠️ 无新闻数据目录")
        return None

    dbs = sorted([f for f in os.listdir(news_dir) if f.endswith(".db")])
    daily_counts = []
    labels = []

    for db_name in dbs[-7:]:
        try:
            conn = sqlite3.connect(os.path.join(news_dir, db_name))
            count = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
            conn.close()
            daily_counts.append(count)
            labels.append(db_name.replace(".db", "")[-5:])
        except:
            daily_counts.append(0)
            labels.append(db_name[-7:-3])

    if not daily_counts:
        return None

    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    colors = ["#60a5fa"] * len(daily_counts)
    ax.bar(range(len(daily_counts)), daily_counts, color=colors, width=0.6, alpha=0.8)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9, color="#8888aa")
    ax.tick_params(colors="#8888aa")
    for spine in ax.spines.values():
        spine.set_color("#2a2a4a")

    ax.set_title("每日新闻采集量", color="#e0e0e0", fontsize=14, pad=15)
    ax.set_ylabel("条数", color="#8888aa")

    path = os.path.join(output_dir, "news_volume.png")
    plt.tight_layout()
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"  ✅ 新闻量图: {path} ({os.path.getsize(path)/1024:.0f} KB)")
    return path


def chart_decision_ratio(output_dir: str):
    """决策分布饼图"""
    try:
        conn = sqlite3.connect("/root/projects/data/invest/fund_data.db")
        # 如果有 decisions 表
        try:
            buy = conn.execute("SELECT COUNT(*) FROM decisions WHERE action='buy'").fetchone()[0]
            sell = conn.execute("SELECT COUNT(*) FROM decisions WHERE action='sell'").fetchone()[0]
            hold = conn.execute("SELECT COUNT(*) FROM decisions WHERE action='hold'").fetchone()[0]
        except:
            buy, sell, hold = 0, 0, 0
        conn.close()

        if buy + sell + hold == 0:
            return None

        fig, ax = plt.subplots(figsize=(5, 4))
        fig.patch.set_facecolor("#1a1a2e")
        colors_pie = ["#4ade80", "#f87171", "#fbbf24"]
        wedges, texts, autotexts = ax.pie(
            [buy, sell, hold], labels=["买入", "卖出", "持有"],
            colors=colors_pie, autopct="%1.0f%%", startangle=90,
            textprops={"color": "#e0e0e0", "fontsize": 11}
        )
        ax.set_title("交易决策分布", color="#e0e0e0", fontsize=14, pad=15)

        path = os.path.join(output_dir, "decision_ratio.png")
        plt.tight_layout()
        plt.savefig(path, dpi=120, bbox_inches="tight", transparent=False)
        plt.close()
        print(f"  ✅ 决策分布图: {path}")
        return path
    except Exception as e:
        print(f"  ⚠️ 决策图生成失败: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="自动图表生成")
    parser.add_argument("--sentiment", action="store_true", help="仅生成情绪趋势图")
    parser.add_argument("--news", action="store_true", help="仅生成新闻量图")
    parser.add_argument("--output", default=str(CHART_DIR), help="输出目录")
    args = parser.parse_args()

    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 50)
    print("  📊 自动图表生成")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  输出: {output_dir}")
    print("=" * 50)

    generated = []

    if args.sentiment:
        p = chart_sentiment(output_dir)
        if p: generated.append(p)
    elif args.news:
        p = chart_news_volume(output_dir)
        if p: generated.append(p)
    else:
        for fn in [chart_sentiment, chart_news_volume, chart_decision_ratio]:
            p = fn(output_dir)
            if p: generated.append(p)

    print(f"\n  共生成 {len(generated)} 张图表")
    for g in generated:
        print(f"    {g}")


if __name__ == "__main__":
    main()
