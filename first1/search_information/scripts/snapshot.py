#!/usr/bin/env python3
"""
每日项目快照生成器 — 写入 CURRENT.md

运行:
  python3 snapshot.py                          # 生成到服务器
  python3 snapshot.py --local /path/to/repo    # 同时写到本地仓库

安装 cron（每天23:55）:
  55 23 * * * cd /root/projects/scripts && python3 snapshot.py >> /var/log/snapshot.log 2>&1
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime


# ── 路径配置 ──
PATHS = {
    "sentiment_history": "/root/projects/data/invest/sentiment/sentiment_history.json",
    "signals": "/root/projects/data/invest/knowledge/signals.json",
    "buffer_dir": "/root/projects/data/search_information/training_buffer",
    "news_dir": "/root/projects/data/search_information/news",
    "rss_dir": "/root/projects/data/search_information/rss",
    "fund_db": "/root/projects/data/invest/fund_data.db",
    "invest_scripts": "/root/projects/invest/scripts",
    "output": "/root/projects/CURRENT.md",
}


def sh(cmd, timeout=10):
    """Run shell command, return output"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def get_container_status():
    """获取容器运行状态"""
    raw = sh("docker ps --format '{{.Names}}\t{{.Status}}'")
    containers = []
    for line in raw.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            ok = "Up" in parts[1]
            containers.append((parts[0], "✅" if ok else "❌", parts[1][:25]))
    return containers


def get_sentiment():
    """情绪历史"""
    path = PATHS["sentiment_history"]
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def get_signals():
    """话题信号"""
    path = PATHS["signals"]
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    return data.get("topics", {})


def get_buffer_count():
    """缓冲池未导出条数"""
    bd = PATHS["buffer_dir"]
    if not os.path.exists(bd):
        return 0
    total = 0
    for f in os.listdir(bd):
        if f.endswith(".jsonl") and "exported" not in f:
            fp = os.path.join(bd, f)
            if os.path.isfile(fp):
                total += sum(1 for _ in open(fp))
    return total


def get_news_db_count():
    """新闻DB统计"""
    nd = PATHS["news_dir"]
    if not os.path.exists(nd):
        return 0, []
    dbs = sorted([f for f in os.listdir(nd) if f.endswith(".db")])
    today_count = 0
    today = datetime.now().strftime("%Y-%m-%d")
    today_db = os.path.join(nd, "%s.db" % today)
    if os.path.exists(today_db):
        try:
            c = sqlite3.connect(today_db)
            today_count = c.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
            c.close()
        except Exception:
            pass
    return len(dbs), today_count


def get_news_sentiment_stats():
    """news_sentiment 表统计"""
    db = PATHS["fund_db"]
    if not os.path.exists(db):
        return 0, []
    try:
        c = sqlite3.connect(db)
        total = c.execute("SELECT COUNT(*) FROM news_sentiment").fetchone()[0]
        dates = [r[0] for r in c.execute("SELECT DISTINCT date FROM news_sentiment ORDER BY date").fetchall()]
        c.close()
        return total, dates
    except Exception:
        return 0, []


def get_db_stats():
    """各表数据量"""
    db = PATHS["fund_db"]
    if not os.path.exists(db):
        return {}
    try:
        c = sqlite3.connect(db)
        stats = {}
        for t in ["news_sentiment", "fund_nav", "fund_info", "decisions"]:
            try:
                n = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                stats[t] = n
            except Exception:
                pass
        c.close()
        return stats
    except Exception:
        return {}


def get_sentinel_stats():
    """从容器日志获取哨兵运行统计"""
    raw = sh("docker logs trendradar 2>&1 | grep '哨兵.*完成' | tail -1")
    return raw.strip() if raw else "无哨兵数据"


def get_sentinel_models_status():
    """检查哨兵模型状态"""
    ok = sh("docker exec trendradar ls /app/models/sentiment/model.onnx 2>/dev/null && echo yes || echo no")
    return "✅已加载" if ok == "yes" else "❌缺失"


def get_deepseek_status():
    """检查 DeepSeek 是否正常"""
    raw = sh("docker logs trendradar 2>&1 | grep -E 'AI.*分析完成|AI.*分析失败' | tail -1")
    if not raw:
        return "⏳ 等待首次分析"
    return "✅ 正常" if "分析完成" in raw else "⚠️ 异常"


def get_git_log():
    """最近 git 提交"""
    repo = "/root/projects"
    if os.path.exists(os.path.join(repo, ".git")):
        log = sh("cd %s && git log --oneline -5 2>/dev/null" % repo)
        return log.splitlines()
    return []


def get_recent_changes():
    """从 scripts 目录找最近修改的文件"""
    scripts = PATHS["invest_scripts"].replace("/invest/scripts", "")
    recent = []
    for root, dirs, files in os.walk(scripts[:scripts.rfind("/")]):
        for f in files:
            if f.endswith((".py", ".sh", ".md")):
                fp = os.path.join(root, f)
                mtime = os.path.getmtime(fp)
                age = (datetime.now().timestamp() - mtime) / 86400
                if age < 5:
                    recent.append((age, f[:40]))
    recent.sort()
    return [f for age, f in recent[:10]]


def main():
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    hostname = socket.gethostname()

    containers = get_container_status()
    sentiment = get_sentiment()
    signals = get_signals()
    buffer_count = get_buffer_count()
    db_days, today_news = get_news_db_count()
    ns_total, ns_dates = get_news_sentiment_stats()
    db_stats = get_db_stats()
    git_log = get_git_log()
    recent_changes = get_recent_changes()
    sentinel_last = get_sentinel_stats()
    sentinel_models = get_sentinel_models_status()
    deepseek_status = get_deepseek_status()

    real_days = len([h for h in sentiment if h.get("index", 50) != 50.0])
    today_entry = [h for h in sentiment if h.get("date") == today]
    today_index = today_entry[-1]["index"] if today_entry else None
    today_level = today_entry[-1]["level"] if today_entry else ""
    pred_ready = real_days >= 7
    buffer_pct = min(100, int(buffer_count / 500 * 100))
    all_ok = all("Up" in s for _, ok, s in containers)

    lines = []
    lines.append("# 项目快照 — %s" % today)
    lines.append("")
    lines.append("> 自动生成 | 主机: %s | %s" % (hostname, now.strftime("%H:%M")))
    lines.append("")

    lines.append("## 整体状态")
    lines.append("")
    status_icon = "✅" if all_ok else "⚠️"
    lines.append("| 维度 | 状态 |")
    lines.append("|------|------|")
    lines.append("| 容器 %s | %d/8 运行中" % (status_icon, len(containers)))
    lines.append("| 情绪积累 | %d天（真实值%d天）%s" % (len(sentiment), real_days, "✅ 预测可用" if pred_ready else "⏳ 需%d天" % (7 - real_days)))
    lines.append("| 缓冲池 | %d/500条（%d%%）" % (buffer_count, buffer_pct))
    lines.append("| 话题信号 | %d个话题" % len(signals))
    lines.append("")

    lines.append("## AI 与哨兵")
    lines.append("")
    lines.append("| 项目 | 状态 |")
    lines.append("|------|------|")
    lines.append("| 哨兵模型 | %s |" % sentinel_models)
    lines.append("| DeepSeek | %s |" % deepseek_status)
    lines.append("| 哨兵统计 | %s |" % sentinel_last)
    lines.append("")

    lines.append("## 数据状态")
    lines.append("")
    lines.append("| 数据项 | 数值 |")
    lines.append("|--------|------|")
    if today_index is not None:
        emoji = "🔴" if today_index < 45 else ("🟢" if today_index > 55 else "⚪")
        lines.append("| 今日情绪 | %s %.1f (%s) |" % (emoji, today_index, today_level))
    if ns_total > 0:
        lines.append("| news_sentiment | %d条 (%s) |" % (ns_total, ", ".join(ns_dates)))
    if db_stats:
        for k, v in sorted(db_stats.items()):
            lines.append("| %s | %d |" % (k.replace("_", " "), v))
    lines.append("| 新闻DB | %d天, 今日%s条 |" % (db_days, today_news))
    lines.append("| 缓冲池 | %d/500条 |" % buffer_count)
    lines.append("")

    if sentiment:
        lines.append("## 情绪历史")
        lines.append("")
        lines.append("| 日期 | 指数 | 等级 |")
        lines.append("|------|------|------|")
        for h in sentiment[-10:]:
            d = h["date"]
            idx = h["index"]
            lvl = h["level"]
            today_mark = " ← 今日" if d == today else ""
            lines.append("| %s | %.1f | %s%s |" % (d, idx, lvl, today_mark))
        if len(sentiment) > 10:
            lines.append("| ... | 共%d天，仅显示最近10天 | |" % len(sentiment))
        lines.append("")

    if signals:
        lines.append("## 话题信号")
        lines.append("")
        lines.append("| 话题 | 信号数 | 等级 |")
        lines.append("|------|--------|------|")
        for t, d in sorted(signals.items(), key=lambda x: -x[1].get("signal_count", 0))[:10]:
            cnt = d.get("signal_count", 0)
            level = d.get("status", "关注中")[:6]
            lines.append("| %s | %d | %s |" % (t, cnt, level))
        if len(signals) > 10:
            lines.append("| ... | 共%d个话题 | |" % len(signals))
        lines.append("")

    if containers:
        lines.append("## 容器状态")
        lines.append("")
        lines.append("| 容器 | 状态 |")
        lines.append("|------|------|")
        for name, icon, status in containers:
            lines.append("| %s %s | %s |" % (icon, name, status))
        lines.append("")

    cron_raw = sh("crontab -l 2>/dev/null")
    cron_lines = [l.strip() for l in cron_raw.splitlines() if l.strip() and not l.startswith("#")]
    if cron_lines:
        lines.append("## 定时任务")
        lines.append("")
        for c in cron_lines:
            if len(c) > 80:
                c = c[:77] + "..."
            lines.append("- `%s`" % c)
        lines.append("")

    if recent_changes:
        lines.append("## 近期变更文件")
        lines.append("")
        for f in recent_changes[:8]:
            lines.append("- %s" % f)
        lines.append("")

    if git_log:
        lines.append("## 最近提交")
        lines.append("")
        for c in git_log:
            lines.append("- %s" % c)
        lines.append("")

    if not pred_ready:
        eta = (7 - real_days)
        lines.append("## 📋 预测可用倒计时")
        lines.append("")
        lines.append("还需要 **%d 天** 真实数据积累（当前 %d/7 天）" % (eta, real_days))
        lines.append("预计 **%s** 后预测模块自动生效" % ("%d天" % eta if eta > 0 else "今日"))
        lines.append("")

    lines.append("---")
    lines.append("_快照自动生成于 %s %s_" % (today, now.strftime("%H:%M:%S")))
    lines.append("")

    md = "\n".join(lines)

    output_path = PATHS["output"]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    print("✅ CURRENT.md written (%d bytes, %d lines)" % (len(md), len(lines)))

    if "--local" in sys.argv:
        idx = sys.argv.index("--local")
        if idx + 1 < len(sys.argv):
            local_path = os.path.join(sys.argv[idx + 1], "CURRENT.md")
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(md)
            print("✅ Local copy written to %s" % local_path)

    return md


def generate():
    return main()


if __name__ == "__main__":
    main()
