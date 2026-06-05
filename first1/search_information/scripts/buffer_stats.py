# -*- coding: utf-8 -*-
"""
缓冲池状态查看工具

用法:
    python buffer_stats.py                           # 查看当前状态
    python buffer_stats.py --export                  # 手动触发导出
    python buffer_stats.py --list                    # 列出所有缓存文件
"""

import sys
import json
from pathlib import Path

# 添加 TrendRadar 路径
sys.path.insert(0, str(Path(__file__).resolve().parent / ".." / "TrendRadar"))

from trendradar.ai.training_buffer import get_buffer, AUTO_EXPORT_THRESHOLD


def main():
    import argparse

    parser = argparse.ArgumentParser(description="缓冲池状态查看工具")
    parser.add_argument("--export", action="store_true", help="手动触发导出")
    parser.add_argument("--list", action="store_true", help="列出所有缓冲文件")
    parser.add_argument("--clear", action="store_true", help="清空已导出的缓存")

    args = parser.parse_args()

    buffer = get_buffer()

    if args.list:
        print(f"\n📂 缓冲文件 ({buffer.buffer_dir}):")
        for f in sorted(buffer.buffer_dir.glob("buffer_*.jsonl*")):
            size = f.stat().st_size
            marker = " [已导出]" if ".exported" in f.name else ""
            print(f"  {f.name}  ({size:,} bytes){marker}")

        print(f"\n📦 导出文件 ({buffer.export_dir}):")
        for f in sorted(buffer.export_dir.glob("train_*.jsonl")):
            count = sum(1 for _ in open(f, "r"))
            print(f"  {f.name}  ({count} 条)")

        return

    if args.export:
        count = buffer.get_total_count()
        if count == 0:
            print("缓冲池为空，无需导出")
            return
        # 手动触发：逐天导出
        for f in sorted(buffer.buffer_dir.glob("buffer_*.jsonl")):
            if ".exported" in f.name:
                continue
            today = f.stem.split("_")[1]  # buffer_2026-06-03 → 2026-06-03
            exported_path = buffer.export_dir / f"train_{today}.jsonl"
            if exported_path.exists():
                print(f"  {today}: 已导出过，跳过")
                continue
            try:
                with buffer._lock:
                    buffer._export_to_training_format_locked(f, exported_path)
                f_count = buffer._count_lines(f)
                print(f"  {today}: ✅ 导出 {f_count} 条 → {exported_path.name}")
            except Exception as e:
                print(f"  {today}: ❌ {e}")
        return

    # 默认：显示状态
    stats = buffer.get_stats()
    print(f"\n=== AI 训练缓冲池状态 ===")
    print(f"  缓冲目录:     {stats['buffer_dir']}")
    print(f"  导出目录:     {stats['export_dir']}")
    print(f"  今日未导出:   {stats['today_unexported']} 条")
    print(f"  累计未导出:   {stats['total_unexported']} 条")
    print(f"  已导出训练:   {stats['total_exported']} 条")
    print(f"  自动导出阈值: {stats['auto_export_threshold']} 条")
    print()

    # 列出各天状态
    print("  各天详情:")
    for f in sorted(buffer.buffer_dir.glob("buffer_*.jsonl*")):
        if ".exported" in f.name:
            continue
        today = f.stem.split("_")[1]
        count = sum(1 for _ in open(f, "r"))
        bar = "█" * min(count // 10, 20)
        print(f"    {today}: {count:4d}条 {bar}")
    for f in sorted(buffer.export_dir.glob("train_*.jsonl")):
        count = sum(1 for _ in open(f, "r"))
        print(f"    {f.stem}: ✅ {count}条 已导出")


if __name__ == "__main__":
    main()
