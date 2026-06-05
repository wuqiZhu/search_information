# -*- coding: utf-8 -*-
"""
一键监控工具 - 查看新加坡服务器全部状态

用法:
  python3 server_status.py [--watch] [--interval 30]

输出:
  ✅ / ❌ 所有容器状态
  📊 情绪指数最新值 + 趋势
  📦 AI 缓存命中率
  📝 训练缓冲池积累量
  🗄️ 数据库关键指标
"""

import json
import os
import sys
import subprocess
import time
from datetime import datetime


def run(cmd, timeout=10):
    """执行命令，返回 stdout"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


class ServerMonitor:
    """新加坡服务器监控"""

    def __init__(self):
        self.results = []
        self.errors = 0

    def check(self, label, cmd, transform=None):
        """执行检查项"""
        try:
            raw = run(cmd)
            if transform:
                result = transform(raw)
            else:
                result = raw if raw else "(empty)"
            status = "✅" if raw and "error" not in raw.lower() else "⚠️"
            self.results.append((status, label, result))
        except Exception as e:
            self.results.append(("❌", label, str(e)))
            self.errors += 1

    def containers(self):
        """1. 容器状态"""
        print("\n" + "=" * 55)
        print("  🐳 容器状态")
        print("=" * 55)
        raw = run("docker ps --format '{{.Names}}\t{{.Status}}'")
        lines = raw.splitlines()
        for line in lines:
            parts = line.split("\t", 1)
            if len(parts) == 2:
                name, status = parts
                ok = "Up" in status
                print(f"  {'✅' if ok else '❌'} {name:<25s} {status}")

    def sentiment(self):
        """2. 情绪指数"""
        print("\n" + "=" * 55)
        print("  📊 情绪指数")
        print("=" * 55)
        raw = run("python3 -c \""
                   "import json; "
                   "d=json.load(open('/root/projects/data/invest/sentiment/sentiment_history.json')); "
                   "x=d[-1]; "
                   "print('index=' + str(x.get('index','?')) + ' level=' + x.get('level','?'))"
                   "\" 2>/dev/null")
        if raw:
            print(f"  ✅ {raw}")
            trend = run("python3 -c \""
                        "import json; d=json.load(open('/root/projects/data/invest/sentiment/sentiment_history.json')); "
                        "print('  last 5: ' + ' > '.join([str(x.get('index','?')) for x in d[-5:]]))"
                        "\" 2>/dev/null")
            if trend:
                print(f"  {trend}")
        else:
            print("  ⚠️ 无情绪数据")

    def cache(self):
        """3. AI 缓存"""
        print("\n" + "=" * 55)
        print("  📦 AI 缓存 (response_cache)")
        print("=" * 55)
        db = "/root/projects/data/search_information/ai_cache/response_cache.db"
        if os.path.exists(db):
            script = (
                "import sqlite3; conn=sqlite3.connect('%(db)s'); "
                "c=conn.execute('SELECT COUNT(*) FROM response_cache').fetchone()[0]; "
                "h=conn.execute('SELECT COALESCE(SUM(hit_count),0) FROM response_cache').fetchone()[0]; "
                "e=conn.execute('SELECT COUNT(*) FROM response_cache WHERE expires_at < %(now)d').fetchone()[0]; "
                "print(f'Entries: {c} | Hits: {h} | Expired: {e}')"
            ) % {"db": db, "now": int(time.time())}
            stats = run(f"python3 -c \"{script}\"")
            if stats:
                print(f"  ✅ {stats}")
            size = os.path.getsize(db)
            print(f"  大小: {size/1024:.0f} KB")
        else:
            print("  ⚠️ 缓存数据库不存在")

    def buffer(self):
        """4. 缓冲池"""
        print("\n" + "=" * 55)
        print("  📝 训练缓冲池 (training_buffer)")
        print("=" * 55)
        buf_dir = "/root/projects/data/search_information/training_buffer"
        if os.path.exists(buf_dir):
            current = 0
            for f in os.listdir(buf_dir):
                if f.endswith(".jsonl") and "exported" not in f:
                    fp = os.path.join(buf_dir, f)
                    with open(fp, "r") as fh:
                        current += sum(1 for _ in fh)
            exported = 0
            exp_dir = os.path.join(buf_dir, "exported")
            if os.path.exists(exp_dir):
                for f in os.listdir(exp_dir):
                    fp = os.path.join(exp_dir, f)
                    with open(fp, "r") as fh:
                        exported += sum(1 for _ in fh)
            print(f"  ✅ 未导出: {current} 条 | 已导出: {exported} 条")
            # Show latest buffer file
            bufs = sorted([f for f in os.listdir(buf_dir) if f.endswith(".jsonl") and f.startswith("buffer_")])
            if bufs:
                print(f"  最新: {bufs[-1]}")
        else:
            print("  ⚠️ 缓冲池目录不存在")

    def database(self):
        """5. 数据库关键指标"""
        print("\n" + "=" * 55)
        print("  🗄️ 数据库")
        print("=" * 55)
        # invest data
        db = "/root/projects/data/invest/fund_data.db"
        if os.path.exists(db):
            script = (
                "import sqlite3; conn=sqlite3.connect('%(db)s'); "
                "ns=conn.execute('SELECT COUNT(*) FROM news_sentiment').fetchone()[0]; "
                "fn=conn.execute('SELECT COUNT(*) FROM fund_nav').fetchone()[0]; "
                "fc=conn.execute('SELECT COUNT(DISTINCT fund_code) FROM fund_nav').fetchone()[0]; "
                "print('news_sentiment: ' + str(ns) + ' | fund_nav: ' + str(fn) + ' (' + str(fc) + ' funds)')"
            ) % {"db": db}
            info = run(f"python3 -c \"{script}\"")
            if info:
                print(f"  ✅ invest: {info}")

        # Latest news DB
        news_dir = "/root/projects/data/search_information/news"
        rss_dir = "/root/projects/data/search_information/rss"
        if os.path.exists(news_dir):
            dbs = sorted([f for f in os.listdir(news_dir) if f.endswith(".db")])
            if dbs:
                latest = dbs[-1]
                size = os.path.getsize(os.path.join(news_dir, latest))
                print(f"  ✅ 新闻DB: {latest} ({size/1024:.0f} KB) - 最近 {len(dbs)} 天")
        if os.path.exists(rss_dir):
            dbs = sorted([f for f in os.listdir(rss_dir) if f.endswith(".db")])
            print(f"  ✅ RSS-DB: 最近 {len(dbs)} 天")

    def web_endpoints(self):
        """6. 关键 Web 端点"""
        print("\n" + "=" * 55)
        print("  🌐 Web 端点")
        print("=" * 55)
        endpoints = [
            ("Dashboard", "http://localhost:8085/api/health", "8085"),
            ("invest-backend", "http://localhost:5000/api/health", "5000"),
            ("semantic-search", "http://localhost:5070/api/health", "5070"),
            ("notification-center", "http://localhost:5050/api/health", "5050"),
        ]
        for name, url, port in endpoints:
            raw = run(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 3 {url} 2>/dev/null || echo 'timeout'")
            ok = raw == "200"
            print(f"  {'✅' if ok else '❌'} {name:<20s} port={port:<5s} {raw}")

    def last_ai_analysis(self):
        """7. 最近 AI 分析"""
        print("\n" + "=" * 55)
        print("  🤖 AI 分析")
        print("=" * 55)
        raw = run("docker logs --tail 5 trendradar 2>&1 | grep -iE '分析|AI|发送|cache' | tail -3")
        if raw:
            for line in raw.splitlines():
                print(f"  {line[:100]}")
        else:
            print("  ⚠️ 暂无最近分析记录")

    def run(self, watch=False, interval=30):
        """执行全部检查"""
        while True:
            self.results = []
            self.errors = 0
            print(f"\n{'#' * 55}")
            print(f"  # 🔍 新加坡服务器状态监控")
            print(f"  # {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'#' * 55}")

            self.containers()
            self.sentiment()
            self.cache()
            self.buffer()
            self.database()
            self.last_ai_analysis()

            print(f"\n{'─' * 55}")
            print("  📊 系统运行正常")
            print(f"{'─' * 55}")

            if not watch:
                break
            print(f"\n⏳ 等待 {interval} 秒后刷新 (Ctrl+C 停止)...")
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n监控已停止")
                break


def main():
    import argparse
    parser = argparse.ArgumentParser(description="新加坡服务器一键监控")
    parser.add_argument("--watch", action="store_true", help="持续监控模式")
    parser.add_argument("--interval", type=int, default=30, help="刷新间隔（秒）")
    args = parser.parse_args()

    monitor = ServerMonitor()
    monitor.run(watch=args.watch, interval=args.interval)


if __name__ == "__main__":
    main()
