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
    from flask import Flask, jsonify, render_template_string, request
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


@app.route('/api/archive')
def api_archive():
    """获取归档统计"""
    data_base = Path(os.environ.get("DATA_BASE", "/app/data"))
    archive_dir = data_base / "search_information" / "archive"

    if not archive_dir.exists():
        return jsonify({
            "total_archives": 0,
            "total_size_mb": 0,
            "archives": [],
        })

    archives = []
    total_size = 0
    for zip_file in sorted(archive_dir.glob("*.zip")):
        size = zip_file.stat().st_size
        total_size += size
        archives.append({
            "name": zip_file.name,
            "size_mb": round(size / (1024 * 1024), 2),
        })

    return jsonify({
        "total_archives": len(archives),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "archives": archives,
    })


@app.route('/api/trend')
def api_trend():
    """获取历史趋势数据（用于图表）"""
    days = int(request.args.get('days', 7))
    data_base = Path(os.environ.get("DATA_BASE", "/app/data"))
    news_dir = data_base / "search_information" / "news"

    if not news_dir.exists():
        return jsonify({"labels": [], "datasets": []})

    result = {"labels": [], "news_count": [], "rss_count": []}

    for i in range(days - 1, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        result["labels"].append(date)

        # 查询新闻数量
        db_file = news_dir / f"{date}.db"
        if db_file.exists():
            count = query_db(str(db_file), "SELECT COUNT(*) as count FROM news_items")
            result["news_count"].append(count[0]["count"] if count else 0)
        else:
            result["news_count"].append(0)

        # 查询 RSS 数量
        rss_dir = data_base / "search_information" / "rss"
        rss_db = rss_dir / f"{date}.db"
        if rss_db.exists():
            count = query_db(str(rss_db), "SELECT COUNT(*) as count FROM rss_items")
            result["rss_count"].append(count[0]["count"] if count else 0)
        else:
            result["rss_count"].append(0)

    return jsonify(result)


@app.route('/api/search')
def api_search():
    """搜索新闻"""
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 50))

    if not query:
        return jsonify({"results": [], "total": 0})

    data_base = Path(os.environ.get("DATA_BASE", "/app/data"))
    news_dir = data_base / "search_information" / "news"

    results = []
    for db_file in sorted(news_dir.glob("*.db"), reverse=True)[:7]:  # 搜索最近7天
        rows = query_db(
            str(db_file),
            "SELECT title, platform_id as source, url, created_at as date FROM news_items WHERE title LIKE ? LIMIT ?",
            (f"%{query}%", limit - len(results))
        )
        results.extend(rows)
        if len(results) >= limit:
            break

    return jsonify({"results": results[:limit], "total": len(results)})


@app.route('/api/semantic-search', methods=['POST'])
def api_semantic_search():
    """语义搜索（调用语义搜索API服务）"""
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'error': '缺少query参数'}), 400

    semantic_search_url = os.environ.get('SEMANTIC_SEARCH_URL', 'http://semantic-search:5070')
    
    # 转换参数名：top_k -> limit
    search_params = {
        'query': data.get('query'),
        'limit': data.get('top_k', data.get('limit', 10))
    }
    
    try:
        import requests
        response = requests.post(
            f"{semantic_search_url}/api/search",
            json=search_params,
            timeout=15
        )
        return jsonify(response.json())
    except ImportError:
        return jsonify({'error': 'requests模块未安装'}), 500
    except Exception as e:
        logger.error(f"语义搜索失败: {e}")
        return jsonify({'error': f'语义搜索服务不可用: {str(e)}'}), 503


@app.route('/api/rag-ask', methods=['POST'])
def api_rag_ask():
    """RAG问答（调用语义搜索API服务）"""
    data = request.get_json()
    if not data or 'question' not in data:
        return jsonify({'error': '缺少question参数'}), 400

    semantic_search_url = os.environ.get('SEMANTIC_SEARCH_URL', 'http://semantic-search:5070')
    
    # 转换参数名：question -> query, top_k -> limit
    ask_params = {
        'query': data.get('question'),
        'limit': data.get('top_k', 5)
    }
    
    try:
        import requests
        response = requests.post(
            f"{semantic_search_url}/api/ask",
            json=ask_params,
            timeout=30
        )
        return jsonify(response.json())
    except ImportError:
        return jsonify({'error': 'requests模块未安装'}), 500
    except Exception as e:
        logger.error(f"RAG问答失败: {e}")
        return jsonify({'error': f'语义搜索服务不可用: {str(e)}'}), 503


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - 信息分析系统</title>
    <script src="https://cdn.bootcdn.net/ajax/libs/Chart.js/4.4.7/chart.umd.min.js"></script>
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
            <h2>数据趋势（最近7天）</h2>
            <canvas id="trendChart" height="200"></canvas>
        </div>

        <div class="section">
            <h2>搜索新闻</h2>
            <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                <input type="text" id="searchInput" placeholder="输入关键词搜索..." style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 6px;">
                <button class="refresh-btn" onclick="searchNews()">搜索</button>
            </div>
            <div id="search-results"><div class="empty">输入关键词后点击搜索</div></div>
        </div>

        <div class="section">
            <h2>语义搜索</h2>
            <p style="color: #666; font-size: 14px; margin-bottom: 15px;">使用AI理解语义，找到相关内容</p>
            <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                <input type="text" id="semanticInput" placeholder="输入自然语言查询，如：最近半导体行业有什么新闻？" style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 6px;">
                <button class="refresh-btn" onclick="semanticSearch()">语义搜索</button>
            </div>
            <div id="semantic-results"><div class="empty">输入自然语言查询后点击语义搜索</div></div>
        </div>

        <div class="section">
            <h2>智能问答</h2>
            <p style="color: #666; font-size: 14px; margin-bottom: 15px;">基于知识库的AI问答，支持复杂问题</p>
            <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                <input type="text" id="askInput" placeholder="输入问题，如：上周有哪些关于嵌入式的重要新闻？" style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 6px;">
                <button class="refresh-btn" onclick="ragAsk()">提问</button>
            </div>
            <div id="ask-results"><div class="empty">输入问题后点击提问</div></div>
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

        <div class="section">
            <h2>市场情绪指数（Fear & Greed Index）</h2>
            <div style="display: flex; gap: 20px; align-items: center; margin-bottom: 15px;">
                <div style="text-align: center; min-width: 120px;">
                    <div id="sentiment-gauge" style="font-size: 48px; font-weight: bold; color: #ffcc00;">--</div>
                    <div id="sentiment-level" style="font-size: 16px; font-weight: 500; margin-top: 5px;">加载中</div>
                    <div id="sentiment-trend" style="font-size: 12px; color: #999; margin-top: 3px;"></div>
                </div>
                <div style="flex: 1;">
                    <canvas id="sentimentRadar" height="200"></canvas>
                </div>
            </div>
            <div id="sentiment-details" style="font-size: 13px; color: #666;"></div>
            <div style="margin-top: 10px;">
                <canvas id="sentimentTrend" height="150"></canvas>
            </div>
        </div>

        <div class="section">
            <h2>数据归档</h2>
            <div id="archive-info"><div class="empty">加载中...</div></div>
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

                loadArchive();
                loadTrend();
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

        async function loadTrend() {
            try {
                const resp = await fetch('/api/trend?days=7');
                const data = await resp.json();

                const ctx = document.getElementById('trendChart').getContext('2d');
                if (window.trendChart) {
                    window.trendChart.destroy();
                }
                window.trendChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.labels,
                        datasets: [
                            {
                                label: '热榜新闻',
                                data: data.news_count,
                                borderColor: '#1a1a2e',
                                backgroundColor: 'rgba(26, 26, 46, 0.1)',
                                tension: 0.4,
                                fill: true
                            },
                            {
                                label: 'RSS 文章',
                                data: data.rss_count,
                                borderColor: '#e94560',
                                backgroundColor: 'rgba(233, 69, 96, 0.1)',
                                tension: 0.4,
                                fill: true
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: {
                                position: 'top',
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    stepSize: 1
                                }
                            }
                        }
                    }
                });
            } catch (e) {
                console.error('加载趋势数据失败:', e);
            }
        }

        async function searchNews() {
            const query = document.getElementById('searchInput').value.trim();
            if (!query) {
                document.getElementById('search-results').innerHTML = '<div class="empty">请输入搜索关键词</div>';
                return;
            }

            try {
                const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=20`);
                const data = await resp.json();
                const el = document.getElementById('search-results');

                if (data.results.length === 0) {
                    el.innerHTML = `<div class="empty">未找到包含"${query}"的新闻</div>`;
                    return;
                }

                el.innerHTML = `<div class="item"><div class="item-title">找到 ${data.total} 条结果</div></div>` +
                    data.results.map(item =>
                        `<div class="item"><div class="item-title">${item.title}</div><div class="item-meta"><span class="badge badge-source">${item.source}</span> ${item.date}</div></div>`
                    ).join('');
            } catch (e) {
                console.error('搜索失败:', e);
            }
        }

        async function semanticSearch() {
            const query = document.getElementById('semanticInput').value.trim();
            if (!query) {
                document.getElementById('semantic-results').innerHTML = '<div class="empty">请输入自然语言查询</div>';
                return;
            }

            const el = document.getElementById('semantic-results');
            el.innerHTML = '<div class="empty">正在语义搜索...</div>';

            try {
                const resp = await fetch('/api/semantic-search', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: query, top_k: 10})
                });
                const data = await resp.json();

                if (data.error) {
                    el.innerHTML = `<div class="empty" style="color:#c00;">${data.error}</div>`;
                    return;
                }

                const results = data.results || [];
                if (results.length === 0) {
                    el.innerHTML = '<div class="empty">未找到相关内容</div>';
                    return;
                }

                el.innerHTML = `<div class="item"><div class="item-title">找到 ${results.length} 条相关结果</div></div>` +
                    results.map(item =>
                        `<div class="item">
                            <div class="item-title">${item.title || '无标题'}</div>
                            <div style="font-size:13px; color:#555; margin:4px 0;">${(item.summary || item.content || '').substring(0, 150)}...</div>
                            <div class="item-meta">
                                <span class="badge badge-score">相关度 ${((item.score || 0) * 100).toFixed(0)}%</span>
                                ${item.category ? `<span class="badge badge-source">${item.category}</span>` : ''}
                                ${item.date || ''}
                            </div>
                        </div>`
                    ).join('');
            } catch (e) {
                console.error('语义搜索失败:', e);
                el.innerHTML = `<div class="empty" style="color:#c00;">语义搜索服务不可用</div>`;
            }
        }

        async function ragAsk() {
            const question = document.getElementById('askInput').value.trim();
            if (!question) {
                document.getElementById('ask-results').innerHTML = '<div class="empty">请输入问题</div>';
                return;
            }

            const el = document.getElementById('ask-results');
            el.innerHTML = '<div class="empty">正在思考中...</div>';

            try {
                const resp = await fetch('/api/rag-ask', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({question: question, top_k: 5})
                });
                const data = await resp.json();

                if (data.error) {
                    el.innerHTML = `<div class="empty" style="color:#c00;">${data.error}</div>`;
                    return;
                }

                let html = `<div class="item">
                    <div class="item-title" style="font-size:15px; line-height:1.8;">${(data.answer || '').replace(/\n/g, '<br>')}</div>
                    <div class="item-meta" style="margin-top:10px;">
                        <span class="badge badge-score">置信度 ${((data.confidence || 0) * 100).toFixed(0)}%</span>
                    </div>
                </div>`;

                if (data.sources && data.sources.length > 0) {
                    html += `<div style="margin-top:10px; padding-top:10px; border-top:1px solid #eee;">
                        <div style="font-size:12px; color:#999; margin-bottom:8px;">参考来源：</div>
                        ${data.sources.map((s, i) =>
                            `<div class="item" style="padding:5px 0;">
                                <span style="color:#1a1a2e; font-weight:500;">[${i+1}]</span>
                                ${s.title || ''}
                                ${s.category ? `<span class="badge badge-source" style="margin-left:5px;">${s.category}</span>` : ''}
                                ${s.date ? `<span style="color:#999; font-size:11px; margin-left:5px;">${s.date}</span>` : ''}
                            </div>`
                        ).join('')}
                    </div>`;
                }

                el.innerHTML = html;
            } catch (e) {
                console.error('RAG问答失败:', e);
                el.innerHTML = `<div class="empty" style="color:#c00;">问答服务不可用</div>`;
            }
        }

        document.getElementById('semanticInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') semanticSearch();
        });
        document.getElementById('askInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') ragAsk();
        });

        // 回车搜索
        document.getElementById('searchInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                searchNews();
            }
        });

        async function loadArchive() {
            try {
                const resp = await fetch('/api/archive');
                const data = await resp.json();
                const el = document.getElementById('archive-info');
                if (data.total_archives === 0) {
                    el.innerHTML = '<div class="empty">暂无归档数据（数据保留30天后自动归档）</div>';
                    return;
                }
                let html = `<div class="item"><div class="item-title">共 ${data.total_archives} 个归档文件，总大小 ${data.total_size_mb} MB</div></div>`;
                data.archives.forEach(a => {
                    html += `<div class="item"><div class="item-title">${a.name}</div><div class="item-meta">${a.size_mb} MB</div></div>`;
                });
                el.innerHTML = html;
            } catch (e) {
                console.error('加载归档信息失败:', e);
            }
        }

        async function fetchWithTimeout(url, options = {}, timeout = 5000) {
            const controller = new AbortController();
            const id = setTimeout(() => controller.abort(), timeout);
            try {
                const resp = await fetch(url, {...options, signal: controller.signal});
                clearTimeout(id);
                return resp;
            } catch(e) {
                clearTimeout(id);
                throw e;
            }
        }

        async function loadSentiment() {
            try {
                const investUrl = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
                    ? 'http://localhost:5000' : 'http://invest-backend:5000';

                const resp = await fetchWithTimeout(`${investUrl}/api/market-sentiment`, {}, 5000);
                if (!resp.ok) return;
                const data = await resp.json();

                const gauge = document.getElementById('sentiment-gauge');
                const level = document.getElementById('sentiment-level');
                const trend = document.getElementById('sentiment-trend');
                const details = document.getElementById('sentiment-details');

                gauge.textContent = data.index.toFixed(0);
                level.textContent = data.level;
                trend.textContent = `趋势: ${data.trend || '平稳'}`;

                const colorMap = {
                    '极度恐惧': '#00cc44', '恐惧': '#88cc00', '中性': '#ffcc00',
                    '贪婪': '#ff8800', '极度贪婪': '#ff4444'
                };
                gauge.style.color = colorMap[data.level] || '#ffcc00';

                if (data.components) {
                    const comp = data.components;
                    const labels = ['新闻情绪', '市场动量', '波动率', '技术信号', '社交情绪'];
                    const keys = ['news_sentiment', 'market_momentum', 'volatility', 'technical_signals', 'social_sentiment'];
                    const scores = keys.map(k => (comp[k]?.score || 0) * 100);

                    if (window.sentimentRadarChart) window.sentimentRadarChart.destroy();
                    const ctx = document.getElementById('sentimentRadar').getContext('2d');
                    window.sentimentRadarChart = new Chart(ctx, {
                        type: 'radar',
                        data: {
                            labels: labels,
                            datasets: [{
                                label: '情绪维度',
                                data: scores,
                                backgroundColor: 'rgba(26, 26, 46, 0.15)',
                                borderColor: '#1a1a2e',
                                pointBackgroundColor: '#1a1a2e',
                            }]
                        },
                        options: {
                            responsive: true,
                            scales: { r: { min: 0, max: 100, ticks: { stepSize: 20 } } },
                            plugins: { legend: { display: false } }
                        }
                    });

                    details.innerHTML = keys.map((k, i) => {
                        const nameMap = {news_sentiment:'新闻情绪',market_momentum:'市场动量',volatility:'波动率',technical_signals:'技术信号',social_sentiment:'社交情绪'};
                        const d = comp[k] || {};
                        return `<span style="margin-right:15px;">${nameMap[k]}: <b>${scores[i].toFixed(0)}</b> (${(d.weight*100).toFixed(0)}%)</span>`;
                    }).join('');
                }

                const histResp = await fetchWithTimeout(`${investUrl}/api/market-sentiment?action=history&days=30`, {}, 5000);
                if (histResp.ok) {
                    const histData = await histResp.json();
                    const history = histData.history || [];
                    if (history.length > 1) {
                        if (window.sentimentTrendChart) window.sentimentTrendChart.destroy();
                        const ctx2 = document.getElementById('sentimentTrend').getContext('2d');
                        window.sentimentTrendChart = new Chart(ctx2, {
                            type: 'line',
                            data: {
                                labels: history.map(h => h.date ? h.date.substring(5) : ''),
                                datasets: [{
                                    label: '情绪指数',
                                    data: history.map(h => h.index),
                                    borderColor: '#1a1a2e',
                                    backgroundColor: 'rgba(26, 26, 46, 0.1)',
                                    tension: 0.4, fill: true,
                                }]
                            },
                            options: {
                                responsive: true,
                                scales: { y: { min: 0, max: 100 } },
                                plugins: { legend: { display: false } }
                            }
                        });
                    }
                }
            } catch (e) {
                console.log('市场情绪指数加载跳过:', e.message);
            }
        }

        loadData();
        loadSentiment();
        setInterval(loadData, 60000);
        setInterval(loadSentiment, 300000);
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
