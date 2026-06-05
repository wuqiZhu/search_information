# -*- coding: utf-8 -*-
"""
跨源信号验证器

当信号出现时，检查是否有多个独立来源印证。
跨源验证规则:
  - 1个来源 → ⚪ 参考
  - 2个来源 → 🟡 关注
  - 3+个来源 → 🔴 重大
  - AI分析结果与新闻趋势一致 → 升级一级
  - 矛盾 → 降级一级

用法:
  python3 cross_validate.py                    # 验证所有话题
  python3 cross_validate.py --topic 半导体      # 验证特定话题
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/root/projects/invest/scripts")
from signal_tracker import get_tracker


SIGNAL_FILE = Path("/root/projects/data/invest/knowledge/signals.json")


def validate_topic(topic: str):
    """验证单个话题的跨源一致性"""
    tracker = get_tracker()
    data = tracker.get_topic(topic)
    signals = data.get("signals", [])
    news = data.get("related_news", [])

    if not signals and not news:
        print(f"  📭 话题「{topic}」暂无数据")
        return

    # 统计来源和信号等级
    sources = set()
    signal_counts = {"🔴": 0, "🟡": 0, "⚪": 0}
    for s in signals:
        src = s.get("source_type", "unknown")
        if src == "新闻":
            sources.add("news")
        elif src == "RSS":
            sources.add("rss")
        lvl = s.get("level", "⚪")
        if lvl in signal_counts:
            signal_counts[lvl] += 1

    # 检查是否有重复新闻（不同平台同一话题）
    titles_seen = set()
    duplicates = 0
    for n in news:
        t = n.get("title", "")[:30]
        if t in titles_seen:
            duplicates += 1
        titles_seen.add(t)

    print(f"\n  🔗 话题: {topic}")
    print(f"  📊 信号分布: 🔴{signal_counts['🔴']} 🟡{signal_counts['🟡']} ⚪{signal_counts['⚪']}")
    print(f"  📰 相关新闻: {len(news)}条, 跨源印证: {len(sources)}个来源")
    print(f"  🔄 重复新闻: {duplicates}条")

    # 交叉验证结论
    if signal_counts["🔴"] >= 3 and len(sources) >= 2:
        conclusion = "🔴 多方印证的重大信号，建议关注"
    elif signal_counts["🔴"] >= 1 and len(sources) >= 3:
        conclusion = "🔴 多源交叉印证，可靠性高"
    elif signal_counts["🟡"] >= 3 and duplicates >= 2:
        conclusion = "🟡 多平台提及但内容趋同，需进一步确认"
    elif signal_counts["🟡"] >= 1:
        conclusion = "🟡 有信号但源不足，持续跟踪"
    elif signal_counts["⚪"] >= 1:
        conclusion = "⚪ 背景信息级，暂无明确指向"
    else:
        conclusion = "ℹ️ 信息不足，无法形成判断"

    print(f"  📋 结论: {conclusion}")

    # 升级/降级建议
    upgraded = 0
    downgraded = 0
    for s in signals:
        lvl = s.get("level", "⚪")
        if lvl == "🔴" and len(sources) < 2:
            upgraded += 1  # should actually be "consider downgrade"
    if upgraded > 0:
        print(f"  ⚠️  建议: {upgraded}条🔴信号仅有1个来源，考虑降级为🟡")

    return conclusion


def validate_all():
    """验证所有话题"""
    tracker = get_tracker()
    topics = tracker.get_all_topics()

    if not topics:
        print("暂无话题数据")
        return

    print(f"\n{'='*55}")
    print("  🔬 跨源信号验证")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")

    for t in topics:
        name = t["name"]
        validate_topic(name)

    print(f"\n{'='*55}")
    print("  验证完成")
    print(f"{'='*55}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="跨源信号验证")
    parser.add_argument("--topic", type=str, help="验证特定话题")
    args = parser.parse_args()

    if args.topic:
        validate_topic(args.topic)
    else:
        validate_all()


if __name__ == "__main__":
    main()
