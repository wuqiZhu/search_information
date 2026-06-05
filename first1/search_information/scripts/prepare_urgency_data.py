# -*- coding: utf-8 -*-
"""
紧急度训练数据准备脚本 — 从热榜历史数据构造 LoRA-C 训练集

从 TrendRadar 的 SQLite 数据库中提取排名变化轨迹，自动标注紧急度标签。

用法:
  python3 prepare_urgency_data.py \
    --news-dir /root/projects/data/search_information/news \
    --output /root/lora_data/urgency
"""

import json
import os
import sqlite3
import random
from datetime import datetime, timedelta
from collections import defaultdict


def get_all_dbs(news_dir: str):
    """获取所有新闻数据库文件"""
    dbs = []
    for f in sorted(os.listdir(news_dir)):
        if f.endswith(".db") and f >= "2026-05-01.db":
            dbs.append(os.path.join(news_dir, f))
    return dbs


def extract_rank_trajectories(db_path: str, min_samples: int = 3):
    """从单日数据库中提取排名轨迹"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查是否有 rank_history 表
        tables = [r[0] for r in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "rank_history" not in tables:
            return []

        # 获取平台的新闻排名历史
        date_str = os.path.basename(db_path).replace(".db", "")

        query = """
            SELECT rh.rank, ni.platform_id, rh.crawl_time,
                   ni.title, ni.url
            FROM rank_history rh
            JOIN news_items ni ON rh.news_item_id = ni.id
            ORDER BY ni.platform_id, ni.url, rh.crawl_time
        """
        rows = cursor.execute(query).fetchall()
        conn.close()

        # 按 url + platform 分组
        groups = defaultdict(list)
        for rank, platform, ts, title, url in rows:
            groups[(url, platform)].append({
                "rank": rank,
                "ts": ts,
                "title": title,
                "platform": platform,
            })

        # 过滤出有足够采样点的
        trajectories = []
        for (url, platform), points in groups.items():
            if len(points) >= min_samples and points[0]["title"]:
                trajectories.append({
                    "title": points[0]["title"][:200],
                    "url": url,
                    "platform": platform,
                    "date": date_str,
                    "ranks": [p["rank"] for p in points],
                    "timestamps": [p["ts"] for p in points],
                    "first_rank": points[0]["rank"],
                    "last_rank": points[-1]["rank"],
                    "best_rank": min(p["rank"] for p in points),
                })

        return trajectories

    except Exception as e:
        print(f"  ⚠️ {os.path.basename(db_path)}: {e}")
        return []


def label_urgency(traj: dict) -> str:
    """
    根据排名轨迹自动标注紧急度：

    high  = 排名飙升（从低位到前5, 或涨幅>10位）
    medium = 排名持续上升（涨幅5-10位）
    low   = 排名稳定/下降/无变化

    Returns: high / medium / low
    """
    ranks = traj["ranks"]
    first = ranks[0]
    last = ranks[-1]
    best = min(ranks)
    improvement = first - last  # 正数 = 排名上升

    # 关键特征
    top5_reached = best <= 5
    surged = improvement >= 10
    rising = 5 <= improvement < 10
    stable = abs(improvement) < 5
    dropped = improvement < 0

    # 高紧急度：飙升至前列
    if top5_reached and surged:
        return "high"
    if top5_reached and first > 10:
        return "high"
    if surged and last <= 10:
        return "high"

    # 中紧急度：持续上升
    if rising:
        return "medium"
    if top5_reached and not dropped:
        return "medium"
    if improvement > 0 and last <= 15:
        return "medium"

    # 低紧急度
    if stable or dropped:
        return "low"
    if last > 20:
        return "low"

    return "low"


def prepare_dataset(news_dir: str, output_dir: str,
                    max_samples: int = 50000):
    """
    准备紧急度训练数据集。

    Args:
        news_dir: 新闻数据库目录
        output_dir: 输出目录
        max_samples: 最大样本数
    """
    os.makedirs(output_dir, exist_ok=True)

    dbs = get_all_dbs(news_dir)
    print(f"找到 {len(dbs)} 个数据库文件")

    samples = []
    for db_path in dbs:
        date_str = os.path.basename(db_path).replace(".db", "")
        print(f"处理 {date_str}...")
        trajectories = extract_rank_trajectories(db_path)
        for traj in trajectories:
            label = label_urgency(traj)
            samples.append({
                "title": traj["title"],
                "platform": traj["platform"],
                "rank_change": f"{traj['first_rank']}→{traj['last_rank']}",
                "cross_platform": 1,  # 简化
                "label": label,
                "source": {
                    "date": traj["date"],
                    "first_rank": traj["first_rank"],
                    "last_rank": traj["last_rank"],
                    "best_rank": traj["best_rank"],
                },
            })

        if len(samples) >= max_samples:
            break

    print(f"\n共提取 {len(samples)} 条样本")

    # 统计标签分布
    from collections import Counter
    dist = Counter(s["label"] for s in samples)
    print(f"标签分布: {dict(dist)}")

    # 打乱
    random.shuffle(samples)

    # 划分 90/10
    split = int(len(samples) * 0.9)
    for name, data in [("train", samples[:split]), ("val", samples[split:])]:
        path = os.path.join(output_dir, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"  已保存 {name}: {len(data)} 条 -> {path}")

    # 标签映射
    label_map_path = os.path.join(output_dir, "labels.json")
    with open(label_map_path, "w") as f:
        json.dump({
            "task": "urgency",
            "labels": ["high", "medium", "low"],
            "num_labels": 3,
            "samples": len(samples),
            "distribution": dict(dist),
        }, f, indent=2)
    print(f"  标签映射: {label_map_path}")

    print("\n✅ 紧急度数据准备完成!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="紧急度训练数据准备")
    parser.add_argument("--news-dir",
                        default="/root/projects/data/search_information/news",
                        help="新闻数据库目录")
    parser.add_argument("--output", default="/root/lora_data/urgency",
                        help="输出目录")
    parser.add_argument("--max-samples", type=int, default=50000,
                        help="最大样本数")
    args = parser.parse_args()
    prepare_dataset(args.news_dir, args.output, args.max_samples)
