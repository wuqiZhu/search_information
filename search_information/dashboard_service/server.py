"""统一 Web Dashboard 服务

聚合四个项目的数据，提供统一的 Web 界面。

使用方式：
    python -m dashboard_service.server
    # 访问 http://localhost:5060
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

try:
    from flask import Flask, jsonify, render_template_string
except ImportError:
    print("请安装 Flask: pip install flask")
    raise

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 数据库路径配置
DB_PATHS = {
    "trendradar": os.environ.get("TRENDRADAR_DB", "../TrendRadar/data/trendradar.db"),
    "rss": os.environ.get("RSS_DB", "../TrendRadar/data/rss.db"),
    "analyse": os.environ.get("ANALYSE_DB", "../analyse_information/data/analyzed.db"),
    "jobs": os.environ.get("JOBS_DB", "../find_job/data/jobs.db"),
    "invest": os.environ.get("INVEST_DB", "../invest/data/fund_data.db"),
}


def find_latest_db(directory: str, pattern: str = "*.db") -> str:
    """查找目录中最新的数据库文件"""
    try:
        dir_path = Path(directory)
        if not dir_path.exists():
            return ""
        db_files = sorted(dir_path.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
        return str(db_files[0]) if db_files else ""
    except Exception:
        return ""


def query_db(db_path: str, sql: str, params: tuple = ()) -> list:
    """安全查询数据库"""
    try:
        path = Path(db_path)
        if not path.exists():
            return []
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql, params)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    except Exception as e:
        logger.warning(f"数据库查询失败 {db_path}: {e}")
        return []


# API 路由

@app.route('/api/today')
def api_today():
    """获取今日数据概览"""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # TrendRadar 今日数据
    trend_count = query_db(
        DB_PATHS["trendradar"],
        "SELECT COUNT(*) as count FROM news_items WHERE created_at >= ?",
        (today,)
    )
    trend_signals = query_db(
        DB_PATHS["trendradar"],
        "SELECT title, platform_id as source, url, created_at as date FROM news_items WHERE created_at >= ? ORDER BY created_at DESC LIMIT 20",
        (today,)
    )

    # RSS 数据
    rss_count = query_db(
        DB_PATHS["rss"],
        "SELECT COUNT(*) as count FROM rss_items WHERE created_at >= ?",
        (today,)
    )

    # 分析数据
    analyse_count = query_db(
        DB_PATHS["analyse"],
        "SELECT COUNT(*) as count FROM analyzed WHERE created_at >= ?",
        (today,)
    )
    analyse_high = query_db(
        DB_PATHS["analyse"],
        "SELECT title, score, category FROM analyzed WHERE created_at >= ? AND score >= 7 ORDER BY score DESC LIMIT 10",
        (today,)
    )

    # 求职数据
    job_count = query_db(
        DB_PATHS["jobs"],
        "SELECT COUNT(*) as count FROM jobs WHERE scraped_at >= ?",
        (today,)
    )
    job_high = query_db(
        DB_PATHS["jobs"],
        "SELECT title, company, score, url FROM jobs WHERE scraped_at >= ? AND score >= 70 ORDER BY score DESC LIMIT 10",
        (today,)
    )

    # 投资数据
    invest_alerts = query_db(
        DB_PATHS["invest"],
        "SELECT fund_name, alert_type, message FROM alerts WHERE date >= ? ORDER BY date DESC LIMIT 10",
        (today,)
    )

    return jsonify({
        "date": today,
        "trendradar": {
            "count": trend_count[0]["count"] if trend_count else 0,
            "signals": trend_signals,
        },
        "rss": {
            "count": rss_count[0]["count"] if rss_count else 0,
        },
        "analyse": {
            "count": analyse_count[0]["count"] if analyse_count else 0,
            "high_score": analyse_high,
        },
        "jobs": {
            "count": job_count[0]["count"] if job_count else 0,
            "high_score": job_high,
        },
        "invest": {
            "alerts": invest_alerts,
        },
    })


@app.route('/api/stats')
def api_stats():
    """获取统计数据"""
    # 各库总数据量
    stats = {}
    for name, path in DB_PATHS.items():
        try:
            if name == "trendradar":
                count = query_db(path, "SELECT COUNT(*) as count FROM news_items")
            elif name == "rss":
                count = query_db(path, "SELECT COUNT(*) as count FROM rss_items")
            elif name == "analyse":
                count = query_db(path, "SELECT COUNT(*) as count FROM analyzed")
            elif name == "jobs":
                count = query_db(path, "SELECT COUNT(*) as count FROM jobs")
            elif name == "invest":
                count = query_db(path, "SELECT COUNT(*) as count FROM fund_data")
            else:
                count = [{"count": 0}]
            stats[name] = count[0]["count"] if count else 0
        except Exception:
            stats[name] = 0

    return jsonify(stats)


@app.route('/api/health')
def api_health():
    """健康检查"""
    db_status = {}
    for name, path in DB_PATHS.items():
        db_status[name] = Path(path).exists()

    return jsonify({
        "status": "ok",
        "databases": db_status,
        "timestamp": datetime.now().isoformat(),
    })


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - 信息分析系统</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; }
        .header { background: #1a1a2e; color: white; padding: 20px; text-align: center; }
        .header h1 { font-size: 24px; }
        .header p { opacity: 0.7; margin-top: 5px; }
        .container { max-width: 1200px; margin: 20px auto; padding: 0 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .stat-card { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .stat-card h3 { font-size: 14px; color: #666; margin-bottom: 10px; }
        .stat-card .number { font-size: 32px; font-weight: bold; color: #1a1a2e; }
        .stat-card .label { font-size: 12px; color: #999; margin-top: 5px; }
        .section { background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .section h2 { font-size: 18px; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #eee; }
        .item { padding: 10px 0; border-bottom: 1px solid #f0f0f0; }
        .item:last-child { border-bottom: none; }
        .item-title { font-weight: 500; }
        .item-meta { font-size: 12px; color: #999; margin-top: 5px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
        .badge-hot { background: #fee; color: #c00; }
        .badge-score { background: #efe; color: #060; }
        .badge-source { background: #eef; color: #006; }
        .empty { text-align: center; padding: 40px; color: #999; }
        .refresh-btn { background: #1a1a2e; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; }
        .refresh-btn:hover { background: #16213e; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Dashboard - 信息分析系统</h1>
        <p id="date">加载中...</p>
    </div>

    <div class="container">
        <div style="text-align: right; margin-bottom: 15px;">
            <button class="refresh-btn" onclick="loadData()">刷新数据</button>
        </div>

        <div class="stats">
            <div class="stat-card">
                <h3>热榜信号</h3>
                <div class="number" id="trend-count">-</div>
                <div class="label">今日匹配</div>
            </div>
            <div class="stat-card">
                <h3>RSS 文章</h3>
                <div class="number" id="rss-count">-</div>
                <div class="label">今日抓取</div>
            </div>
            <div class="stat-card">
                <h3>分析文章</h3>
                <div class="number" id="analyse-count">-</div>
                <div class="label">今日分析</div>
            </div>
            <div class="stat-card">
                <h3>求职岗位</h3>
                <div class="number" id="job-count">-</div>
                <div class="label">今日抓取</div>
            </div>
        </div>

        <div class="section">
            <h2>今日热榜信号</h2>
            <div id="trend-signals"><div class="empty">加载中...</div></div>
        </div>

        <div class="section">
            <h2>高分分析文章</h2>
            <div id="analyse-high"><div class="empty">加载中...</div></div>
        </div>

        <div class="section">
            <h2>高分求职岗位</h2>
            <div id="job-high"><div class="empty">加载中...</div></div>
        </div>

        <div class="section">
            <h2>投资预警</h2>
            <div id="invest-alerts"><div class="empty">加载中...</div></div>
        </div>
    </div>

    <script>
        async function loadData() {
            try {
                const resp = await fetch('/api/today');
                const data = await resp.json();

                document.getElementById('date').textContent = data.date;
                document.getElementById('trend-count').textContent = data.trendradar.count;
                document.getElementById('rss-count').textContent = data.rss.count;
                document.getElementById('analyse-count').textContent = data.analyse.count;
                document.getElementById('job-count').textContent = data.jobs.count;

                renderList('trend-signals', data.trendradar.signals, item =>
                    `<div class="item"><div class="item-title">${item.title}</div><div class="item-meta"><span class="badge badge-source">${item.source}</span> ${item.date}</div></div>`
                );

                renderList('analyse-high', data.analyse.high_score, item =>
                    `<div class="item"><div class="item-title">${item.title}</div><div class="item-meta"><span class="badge badge-score">评分 ${item.score}</span> ${item.category}</div></div>`
                );

                renderList('job-high', data.jobs.high_score, item =>
                    `<div class="item"><div class="item-title">${item.title} - ${item.company}</div><div class="item-meta"><span class="badge badge-score">匹配度 ${item.score}%</span></div></div>`
                );

                renderList('invest-alerts', data.invest.alerts, item =>
                    `<div class="item"><div class="item-title">${item.fund_name}</div><div class="item-meta"><span class="badge badge-hot">${item.alert_type}</span> ${item.message}</div></div>`
                );
            } catch (e) {
                console.error('加载失败:', e);
            }
        }

        function renderList(id, items, template) {
            const el = document.getElementById(id);
            if (!items || items.length === 0) {
                el.innerHTML = '<div class="empty">暂无数据</div>';
                return;
            }
            el.innerHTML = items.map(template).join('');
        }

        loadData();
        setInterval(loadData, 60000);
    </script>
</body>
</html>"""


@app.route('/')
def dashboard():
    """Dashboard 主页"""
    return render_template_string(DASHBOARD_HTML)


def create_app():
    """创建 Flask 应用"""
    # 加载 .env
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key and key not in os.environ:
                        os.environ[key] = value

    # 更新数据库路径（支持自动查找最新数据库）
    # 优先使用环境变量，然后查找最新的数据库文件
    data_base = Path(os.environ.get("DATA_BASE", "/app/data"))

    # TrendRadar 热榜数据库（按日期存储：news/2026-05-27.db）
    trendradar_news_dir = data_base / "search_information" / "news"
    if trendradar_news_dir.exists():
        DB_PATHS["trendradar"] = find_latest_db(str(trendradar_news_dir))
    else:
        DB_PATHS["trendradar"] = os.environ.get("TRENDRADAR_DB", "")

    # RSS 数据库（按日期存储：rss/2026-05-27.db）
    rss_dir = data_base / "search_information" / "rss"
    if rss_dir.exists():
        DB_PATHS["rss"] = find_latest_db(str(rss_dir))
    else:
        DB_PATHS["rss"] = os.environ.get("RSS_DB", "")

    # 分析数据库
    DB_PATHS["analyse"] = os.environ.get("ANALYSE_DB", str(data_base / "knowledge_base" / "analyzed.db"))

    # 求职数据库
    DB_PATHS["jobs"] = os.environ.get("JOBS_DB", str(data_base / "find_job" / "jobs.db"))

    # 投资数据库
    DB_PATHS["invest"] = os.environ.get("INVEST_DB", str(data_base / "invest" / "fund_data.db"))

    logger.info(f"数据库路径: {DB_PATHS}")

    return app


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    app.run(host='0.0.0.0', port=5060, debug=False)
