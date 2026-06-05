#!/usr/bin/env python3
"""
情绪采集保活检查 — 每天检查 sentiment_history 是否正常更新

用法:
  python3 check_sentiment_alive.py              # 检查并报告
  python3 check_sentiment_alive.py --repair     # 尝试修复

安装到cron（每天8/14/20点）:
  0 8,14,20 * * * python3 /root/projects/scripts/check_sentiment_alive.py --cron >> /var/log/sentiment_check.log 2>&1
"""
import json
import os
import sys
from datetime import datetime


HISTORY_FILE = "/root/projects/data/invest/sentiment/sentiment_history.json"


def check(cron=False):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    issues = []

    # 1. 文件是否存在
    if not os.path.exists(HISTORY_FILE):
        issues.append("HISTORY_FILE_MISSING: %s" % HISTORY_FILE)
        if not cron:
            print("[FAIL] History file missing")
        return issues

    # 2. 今天是否有记录
    with open(HISTORY_FILE) as f:
        history = json.load(f)

    today_entry = [h for h in history if h.get("date") == today]
    if not today_entry:
        issues.append("NO_TODAY_ENTRY: %s not in history (%d entries)" % (today, len(history)))

    # 3. 是否是真实值（非默认50.0）
    if today_entry:
        index = today_entry[-1].get("index", 0)
        if index == 50.0:
            issues.append("DEFAULT_VALUE: today index=50.0 (placeholder, not real)")

    # 4. 总记录数是否增长
    if len(history) < 3:
        issues.append("TOO_FEW_RECORDS: only %d days of history" % len(history))

    if not cron:
        print("[%s] Sentiment check: %s" % (now.strftime("%H:%M"), "OK" if not issues else "ISSUES"))
        for h in history:
            marker = " ← TODAY" if h.get("date") == today else ""
            print("  %s: %.1f %s%s" % (h["date"], h["index"], h["level"], marker))
        if issues:
            print("\nIssues:")
            for i in issues:
                print("  ⚠️  %s" % i)
    else:
        if issues:
            print("[%s] %s" % (today, "; ".join(issues)))

    return issues


def main():
    import argparse
    parser = argparse.ArgumentParser(description="情绪采集保活检查")
    parser.add_argument("--cron", action="store_true", help="静默模式")
    parser.add_argument("--repair", action="store_true", help="尝试修复（待实现）")
    args = parser.parse_args()

    issues = check(args.cron)

    if args.repair and issues:
        print("Repair mode: not yet implemented - invest-backend auto-restarts collector")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
