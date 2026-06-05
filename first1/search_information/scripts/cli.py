#!/usr/bin/env python3
"""
统一命令行入口 - 记住这一个命令就够了

用法:
  python cli.py                查看系统概览
  python cli.py --digest       生成今日简报
  python cli.py --topic 话题   查看话题线索
  python cli.py --sentiment    查看情绪详情
  python cli.py --buffer       查看缓冲池
  python cli.py --cache        查看AI缓存统计
  python cli.py --watch        持续监控
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime


def cmd(command, timeout=15):
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def show_status():
    """系统概览"""
    print("\n" + "=" * 50)
    print("  📡 投资情报系统 - 状态概览")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 容器
    raw = cmd("docker ps --format '{{.Names}}\t{{.Status}}'")
    print("\n  🐳 容器:")
    for line in raw.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            ok = "Up" in parts[1]
            print(f"    {'✅' if ok else '❌'} {parts[0]:<25s} {parts[1][:20]}")

    # 情绪指数
    try:
        with open("/root/projects/data/invest/sentiment/sentiment_history.json", "r") as f:
            hist = json.load(f)
        if hist:
            x = hist[-1]
            print(f"\n  📊 情绪指数: {x.get('index','?')} ({x.get('level','?')})")
    except: pass

    # 数据库
    try:
        conn = __import__("sqlite3").connect("/root/projects/data/invest/fund_data.db")
        ns = conn.execute("SELECT COUNT(*) FROM news_sentiment").fetchone()[0]
        fn = conn.execute("SELECT COUNT(*) FROM fund_nav").fetchone()[0]
        print(f"  🗄️  数据库: news_sentiment={ns} fund_nav={fn}")
        conn.close()
    except: pass

    # 缓存
    try:
        db = "/root/projects/data/search_information/ai_cache/response_cache.db"
        if os.path.exists(db):
            conn = __import__("sqlite3").connect(db)
            c = conn.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
            h = conn.execute("SELECT COALESCE(SUM(hit_count),0) FROM response_cache").fetchone()[0]
            print(f"  📦 AI缓存: {c}条目, {h}次命中")
            conn.close()
    except: pass

    # 缓冲池
    bd = "/root/projects/data/search_information/training_buffer"
    if os.path.exists(bd):
        count = sum(1 for f in os.listdir(bd) if f.endswith(".jsonl") and "exported" not in f
                    for _ in open(os.path.join(bd, f)))
        print(f"  📝 缓冲池: {count}条未导出")

    # 新闻
    nd = "/root/projects/data/search_information/news"
    if os.path.exists(nd):
        dbs = sorted([f for f in os.listdir(nd) if f.endswith(".db")])
        if dbs:
            print(f"  📰 新闻DB: {len(dbs)}天, 最新={dbs[-1]}")

    print("=" * 50 + "\n")


def show_digest():
    """生成今日简报"""
    print(f"\n📝 生成今日简报 ({datetime.now().strftime('%Y-%m-%d')})...")
    try:
        # Run the existing digest generation
        r = cmd("docker exec trendradar python3 /app/trendradar/__main__.py --report daily 2>/dev/null | tail -5")
        if r:
            print(r)
        else:
            print("  日报已调度生成，可在 Dashboard 查看")
    except Exception as e:
        print(f"  生成失败: {e}")
    print()


def show_topic(topic):
    """话题线索 - 使用 SignalTracker"""
    try:
        sys.path.insert(0, "/root/projects/invest/scripts")
        from signal_tracker import get_tracker, add_signal
        st = get_tracker()

        # Search in news DB and auto-add signals
        news_dir = "/root/projects/data/search_information/news"
        if os.path.exists(news_dir):
            dbs = sorted([f for f in os.listdir(news_dir) if f.endswith(".db")])
            for db_path in [os.path.join(news_dir, d) for d in dbs[-3:]]:
                try:
                    conn = __import__("sqlite3").connect(db_path)
                    rows = conn.execute(
                        "SELECT title, platform_id, first_crawl_time FROM news_items "
                        "WHERE title LIKE ? ORDER BY first_crawl_time DESC LIMIT 5",
                        ("%" + topic + "%",)
                    ).fetchall()
                    for r in rows:
                        add_signal(topic, "新闻", r[0][:100], "🟡",
                                   source_url="", related_data={"source": r[1], "date": str(r[2])[:10]})
                    conn.close()
                except: pass

        # Get full topic data
        data = st.get_topic(topic)
        info = data.get("info", {})
        signals = data.get("signals", [])
        news = data.get("related_news", [])
        decisions = data.get("related_decisions", [])

        print("")
        print("🔗 话题:", topic)
        print("  状态:", info.get("status", "N/A"))
        print("  信号数:", info.get("signal_count", 0))
        print("  摘要:", data.get("summary", ""))
        print("")

        if signals:
            print("  📊 信号时间线:")
            for s in signals[-10:]:
                lvl = s.get("level", "⚪")
                src = s.get("source_type", "?")
                con = s["content"][:60]
                print("   ", lvl, "[" + src + "]", con)
        if news:
            print("\n  📰 相关新闻:")
            for n in news[:5]:
                print("    -", n["title"][:50], "[" + n.get("source", "?") + "]", n.get("date", ""))
        if decisions:
            print("\n  📋 关联决策:")
            for d in decisions[:3]:
                print("    -", str(d)[:80])
        if not signals and not news:
            print("  📭 暂无「" + topic + "」的相关信息")
        print()
    except Exception as e:
        print("  话题查询失败:", e)
        print()


def show_sentiment():
    """情绪详情"""
    try:
        with open("/root/projects/data/invest/sentiment/sentiment_history.json", "r") as f:
            hist = json.load(f)
        if not hist:
            print("暂无情绪数据")
            return
        x = hist[-1]
        print(f"\n📈 情绪指数详情")
        print(f"  当前: {x.get('index','?')} ({x.get('level','?')})")
        print(f"  趋势: {x.get('trend','?')}")
        print(f"  日期: {x.get('date','?')}")
        if "components" in x:
            for k, v in x["components"].items():
                print(f"    {k}: {v}")
        print(f"\n  近7天:")
        for h in hist[-7:]:
            print(f"    {h.get('date','?')}: {h.get('index','?')}")
        print()
    except Exception as e:
        print(f"读取失败: {e}")


def show_buffer():
    """缓冲池"""
    bd = "/root/projects/data/search_information/training_buffer"
    if not os.path.exists(bd):
        print("缓冲池目录不存在")
        return
    total = 0
    for f in sorted(os.listdir(bd)):
        fp = os.path.join(bd, f)
        if os.path.isfile(fp) and f.endswith(".jsonl") and "exported" not in f:
            c = sum(1 for _ in open(fp))
            total += c
            print(f"  {f}: {c}条")
    exported = 0
    ed = os.path.join(bd, "exported")
    if os.path.exists(ed):
        for f in os.listdir(ed):
            c = sum(1 for _ in open(os.path.join(ed, f)))
            exported += c
            print(f"  📦 exported/{f}: {c}条")
    print(f"\n  总计: 未导出={total} 已导出={exported}")


def show_cache():
    """缓存统计"""
    db = "/root/projects/data/search_information/ai_cache/response_cache.db"
    if not os.path.exists(db):
        print("缓存数据库不存在")
        return
    import sqlite3
    conn = sqlite3.connect(db)
    c = conn.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
    h = conn.execute("SELECT COALESCE(SUM(hit_count),0) FROM response_cache").fetchone()[0]
    e = conn.execute("SELECT COUNT(*) FROM response_cache WHERE expires_at < ?",
                     (__import__("time").time(),)).fetchone()[0]
    conn.close()
    print(f"\n📦 AI响应缓存")
    print(f"  条目: {c}")
    print(f"  命中: {h}")
    print(f"  过期: {e}")
    print(f"  缓存DB: {db}")


def main():
    parser = argparse.ArgumentParser(description="投资情报系统 - 统一命令行")
    parser.add_argument("--digest", action="store_true", help="生成今日简报")
    parser.add_argument("--topic", type=str, help="查看话题线索")
    parser.add_argument("--sentiment", action="store_true", help="查看情绪详情")
    parser.add_argument("--buffer", action="store_true", help="查看缓冲池")
    parser.add_argument("--cache", action="store_true", help="查看AI缓存")
    parser.add_argument("--briefing", action="store_true", help="生成语音简报")
    parser.add_argument("--charts", action="store_true", help="生成图表")
    parser.add_argument("--validate", type=str, nargs="?", const="all", help="跨源信号验证")
    parser.add_argument("--predict", action="store_true", help="市场预测")
    parser.add_argument("--watch", action="store_true", help="持续监控模式")

    args = parser.parse_args()

    if args.digest:
        show_digest()
    elif args.topic:
        show_topic(args.topic)
    elif args.sentiment:
        show_sentiment()
    elif args.buffer:
        show_buffer()
    elif args.cache:
        show_cache()
    elif args.briefing:
        os.system("cd /root/projects/search_information/search_information/scripts && python3 tts_briefing.py --morning")
    elif args.charts:
        os.system("cd /root/projects/search_information/search_information/scripts && python3 charts.py")
    elif args.predict:
        os.system("python3 /root/projects/search_information/search_information/scripts/predictor.py")
    elif args.validate:
        topic = args.validate if args.validate != "all" else ""
        cmd = f"cd /root/projects/search_information/search_information/scripts && python3 cross_validate.py {'--topic ' + topic if topic else ''}"
        os.system(cmd)
    else:
        show_status()
        if args.watch:
            import time
            try:
                while True:
                    time.sleep(30)
                    show_status()
            except KeyboardInterrupt:
                print("\n监控已停止")


if __name__ == "__main__":
    main()
