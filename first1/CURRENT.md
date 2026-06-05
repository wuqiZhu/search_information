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


def get_git_log():
    """最近 git 提交"""
    # 从本地仓库获取
    repo = "/root/projects"
    if os.path.exists(os.path.join(repo, ".git")):
        log = sh("cd %s && git log --oneline -5 2>/dev/null" % repo)
        return log.splitlines()
    return []


def get_recent_changes():
    """从 scripts 目录找最近修改的文件"""
    scripts = PATHS["invest_scripts"].replace("/invest/scripts", "")
    # 找最近3天修改的 .py 文件
    recent = []
    for root, dirs, files in os.walk(scripts[:scripts.rfind("/")]):
        for f in files:
            if f.endswith((".py", ".sh", ".md")):
                fp = os.path.join(root, f)
                mtime = os.path.getmtime(fp)
                age = (datetime.now().timestamp() - mtime) / 86400
                if age < 5:  # 5天内的文件
                    recent.append((age, f[:40]))
    recent.sort()
    return [f for age, f in recent[:10]]


def main():
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    hostname = socket.gethostname()

    # ── 收集数据 ──
    containers = get_container_status()
    sentiment = get_sentiment()
    signals = get_signals()
    buffer_count = get_buffer_count()
    db_days, today_news = get_news_db_count()
    ns_total, ns_dates = get_news_sentiment_stats()
    db_stats = get_db_stats()
    git_log = get_git_log()
    recent_changes = get_recent_changes()
    
    # ── 计算关键指标 ──
    real_days = len([h for h in sentiment if h.get("index", 50) != 50.0])
    today_entry = [h for h in sentiment if h.get("date") == today]
    today_index = today_entry[-1]["index"] if today_entry else None
    today_level = today_entry[-1]["level"] if today_entry else ""
    pred_ready = real_days >= 7
    buffer_pct = min(100, int(buffer_count / 500 * 100))
    all_ok = all("Up" in s for _, ok, s in containers)
    
    # ── 生成 MD ──
    lines = []
    lines.append("# 项目快照 — %s" % today)
    lines.append("")
    lines.append("> 自动生成 | 主机: %s | %s" % (hostname, now.strftime("%H:%M")))
    lines.append("")
    
    # 整体状态
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
    
    # 数据详表
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
    
    # 情绪历史
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
    
    # 话题信号
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
    
    # 容器状态
    if containers:
        lines.append("## 容器状态")
        lines.append("")
        lines.append("| 容器 | 状态 |")
        lines.append("|------|------|")
        for name, icon, status in containers:
            lines.append("| %s %s | %s |" % (icon, name, status))
        lines.append("")
    
    # 定时任务
    cron_raw = sh("crontab -l 2>/dev/null")
    cron_lines = [l.strip() for l in cron_raw.splitlines() if l.strip() and not l.startswith("#")]
    if cron_lines:
        lines.append("## 定时任务")
        lines.append("")
        for c in cron_lines:
            # Truncate long commands
            if len(c) > 80:
                c = c[:77] + "..."
            lines.append("- `%s`" % c)
        lines.append("")
    
    # 最近变更
    if recent_changes:
        lines.append("## 近期变更文件")
        lines.append("")
        for f in recent_changes[:8]:
            lines.append("- %s" % f)
        lines.append("")
    
    # Git 最近提交
    if git_log:
        lines.append("## 最近提交")
        lines.append("")
        for c in git_log:
            lines.append("- %s" % c)
        lines.append("")
    
    # 预测可用时间
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
    
    # ── 写入 ──
    output_path = PATHS["output"]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    print("✅ CURRENT.md written (%d bytes, %d lines)" % (len(md), len(lines)))
    
    # 如果有 --local 参数，也写入本地
    if "--local" in sys.argv:
        idx = sys.argv.index("--local")
        if idx + 1 < len(sys.argv):
            local_path = os.path.join(sys.argv[idx + 1], "CURRENT.md")
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(md)
            print("✅ Local copy written to %s" % local_path)
    
    return md


def generate():
    """供外部调用的生成函数"""
    return main()


if __name__ == "__main__":
    main()
root@ubuntu-s-1vcpu-1gb-35gb-intel-sgp1:~/projects/search_information/search_information/TrendRadar/docker#
root@ubuntu-s-1vcpu-1gb-35gb-intel-sgp1:~/projects/search_information/search_information/TrendRadar/docker# cat > /root/projects/scripts/snapshot.py
^C
root@ubuntu-s-1vcpu-1gb-35gb-intel-sgp1:~/projects/search_information/search_information/TrendRadar/docker# cat /root/projects/CURRENT.md
# 项目快照 — 2026-06-04

> 自动生成 | 主机: ubuntu-s-1vcpu-1gb-35gb-intel-sgp1 | 23:38

## 整体状态

| 维度 | 状态 |
|------|------|
| 容器 ✅ | 8/8 运行中
| 情绪积累 | 5天（真实值2天）⏳ 需5天
| 缓冲池 | 854/500条（100%）
| 话题信号 | 6个话题

## AI 与哨兵

| 项目     | 状态           |
| -------- | -------------- |
| 哨兵模型 | ❌缺失          |
| DeepSeek | ⏳ 等待首次分析 |
| 哨兵统计 | 无哨兵数据     |

## 数据状态

| 数据项         | 数值                            |
| -------------- | ------------------------------- |
| 今日情绪       | 🔴 39.3 (恐惧)                   |
| news_sentiment | 2723条 (2026-06-03, 2026-06-04) |
| fund info      | 0                               |
| fund nav       | 4580                            |
| news sentiment | 2723                            |
| 新闻DB         | 10天, 今日1250条                |
| 缓冲池         | 854/500条                       |

## 情绪历史

| 日期       | 指数 | 等级        |
| ---------- | ---- | ----------- |
| 2026-05-31 | 50.0 | 中性        |
| 2026-06-01 | 50.0 | 中性        |
| 2026-06-02 | 50.0 | 中性        |
| 2026-06-03 | 39.5 | 恐惧        |
| 2026-06-04 | 39.3 | 恐惧 ← 今日 |

## 话题信号

| 话题          | 信号数 | 等级   |
| ------------- | ------ | ------ |
| 半导体        | 27     | 关注中 |
| 公司动态      | 13     | 关注中 |
| 住房政策      | 8      | 关注中 |
| INVESTOR      | 2      | 关注中 |
| 活动报名      | 2      | 关注中 |
| semiconductor | 1      | 关注中 |

## 容器状态

| 容器                  | 状态                  |
| --------------------- | --------------------- |
| ✅ trendradar          | Up About a minute     |
| ✅ dashboard           | Up 26 hours           |
| ✅ invest-backend      | Up 27 hours           |
| ✅ semantic-search     | Up 33 hours           |
| ✅ analyser            | Up 26 minutes         |
| ✅ invest-frontend     | Up 34 hours (healthy) |
| ✅ feedback-learner    | Up 34 hours           |
| ✅ notification-center | Up 34 hours           |

## 定时任务

- `*/30 * * * * cd ~/projects/search_information/search_information/TrendRadar &...`
- `0 * * * * cd ~/projects/invest/scripts && python decision_engine.py --process...`
- `30 * * * * cd ~/projects/invest/scripts && python execution_engine.py --proce...`
- `0 */2 * * * cd ~/projects/Feedback_and_Learning/invest/scripts && python feed...`
- `0 2 * * * find /data -name "*.db" -mtime +30 -exec gzip {} \; >> /data/logs/d...`
- `0 3 * * * find /data/logs -name "*.log" -mtime +30 -delete`
- `0 18 * * * docker exec invest-backend python scripts/update_nav.py >> /var/lo...`
- `0 9 * * * cd /root/projects/search_information/search_information/scripts && ...`
- `0 */2 * * * cd /root/projects/scripts && python3 auto_signals.py --cron >> /v...`
- `0 8,14,20 * * * python3 /root/projects/scripts/check_sentiment_alive.py --cro...`
- `58 23 * * * docker exec invest-backend python -c "from collect_sentiment impo...`
- `55 23 * * * cd /root/projects/scripts && python3 snapshot.py >> /var/log/snap...`

## 近期变更文件

- snapshot.py
- 20260604_151215_Blender_5_2_LTS_Enters_B
- 20260604_151215_One_step_forward__two_st
- __main__.py
- 20260604_141141__Please_do_not_vibe_f___
- 20260604_141130_Qualcomm Gets The Lenovo
- 20260604_141130_Qualcomm Gets The Lenovo
- 20260604_141128_Ask_Hackaday__How_Do_You

## 📋 预测可用倒计时

还需要 **5 天** 真实数据积累（当前 2/7 天）
预计 **5天** 后预测模块自动生效

---
_快照自动生成于 2026-06-04 23:38:46_