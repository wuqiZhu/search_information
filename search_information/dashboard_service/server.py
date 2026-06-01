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


def resolve_db_path(name: str, default_path: str, alternatives: list = None) -> str:
    """智能解析数据库路径，支持多个备选路径"""
    path = Path(default_path)
    if path.exists():
        return default_path
    if alternatives:
        for alt in alternatives:
            alt_path = Path(alt)
            if alt_path.exists():
                return alt
    return default_path


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
        "SELECT title, platform_id as source, url, created_at as date FROM news_items WHERE created_at >= ? AND platform_id NOT IN ('weibo', 'douyin') ORDER BY created_at DESC LIMIT 10",
        (today,)
    )
    if not trend_signals:
        trend_signals = query_db(
            DB_PATHS["trendradar"],
            "SELECT title, platform_id as source, url, created_at as date FROM news_items WHERE created_at >= ? ORDER BY created_at DESC LIMIT 10",
            (today,)
        )

    # RSS 数据
    rss_count = query_db(
        DB_PATHS["rss"],
        "SELECT COUNT(*) as count FROM rss_items WHERE created_at >= ?",
        (today,)
    )

    # 分析数据（兼容 analyzer.db 和 analyzed.db，表名 processed_urls 和 analyzed）
    analyse_db = DB_PATHS["analyse"]
    analyse_count = query_db(
        analyse_db,
        "SELECT COUNT(*) as count FROM processed_urls WHERE created_at >= ?",
        (today,)
    )
    if not analyse_count:
        analyse_count = query_db(
            analyse_db,
            "SELECT COUNT(*) as count FROM analyzed WHERE created_at >= ?",
            (today,)
        )
    analyse_high = query_db(
        analyse_db,
        "SELECT title, score, category FROM processed_urls WHERE created_at >= ? AND score >= 7 ORDER BY score DESC LIMIT 10",
        (today,)
    )
    if not analyse_high:
        analyse_high = query_db(
            analyse_db,
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

    # 投资数据（从现有表生成预警，alerts表不存在时自动降级）
    invest_alerts = query_db(
        DB_PATHS["invest"],
        "SELECT fund_name, alert_type, message FROM alerts WHERE date >= ? ORDER BY date DESC LIMIT 10",
        (today,)
    )
    if not invest_alerts:
        invest_alerts = []
        drawdown_alerts = query_db(
            DB_PATHS["invest"],
            "SELECT fi.fund_name, fa.max_drawdown, fa.annualized_return FROM fund_analysis fa JOIN fund_info fi ON fa.fund_code = fi.fund_code WHERE fa.max_drawdown < -10 ORDER BY fa.analysis_date DESC LIMIT 5"
        )
        for row in drawdown_alerts:
            invest_alerts.append({
                "fund_name": row.get("fund_name", ""),
                "alert_type": "回撤预警",
                "message": f"最大回撤 {row.get('max_drawdown', 0):.1f}%"
            })
        profit_alerts = query_db(
            DB_PATHS["invest"],
            "SELECT fi.fund_name, ir.profit, ir.profit_rate FROM invest_records ir JOIN fund_info fi ON ir.fund_code = fi.fund_code WHERE ir.profit_rate > 15 OR ir.profit_rate < -10 ORDER BY ir.update_time DESC LIMIT 5"
        )
        for row in profit_alerts:
            rate = row.get("profit_rate", 0)
            if rate > 15:
                invest_alerts.append({
                    "fund_name": row.get("fund_name", ""),
                    "alert_type": "止盈提醒",
                    "message": f"收益率 {rate:.1f}%，考虑止盈"
                })
            elif rate < -10:
                invest_alerts.append({
                    "fund_name": row.get("fund_name", ""),
                    "alert_type": "止损提醒",
                    "message": f"亏损 {rate:.1f}%，注意风险"
                })

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
                count = query_db(path, "SELECT COUNT(*) as count FROM processed_urls")
                if not count:
                    count = query_db(path, "SELECT COUNT(*) as count FROM analyzed")
            elif name == "jobs":
                count = query_db(path, "SELECT COUNT(*) as count FROM jobs")
            elif name == "invest":
                count = query_db(path, "SELECT COUNT(*) as count FROM fund_info")
                if not count:
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
    data = request.get_json(silent=True)
    if not data or not data.get('query'):
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
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '无效的JSON数据'}), 400
    question = data.get('question') or data.get('query')
    if not question:
        return jsonify({'error': '缺少question参数'}), 400

    semantic_search_url = os.environ.get('SEMANTIC_SEARCH_URL', 'http://semantic-search:5070')
    
    # 转换参数名：question -> query, top_k -> limit
    ask_params = {
        'query': question,
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


@app.route('/api/market-sentiment')
def api_market_sentiment():
    """代理转发市场情绪API（解决前端跨域问题）"""
    invest_url = os.environ.get('INVEST_API_URL', 'http://invest-backend:5000')
    action = request.args.get('action', 'latest')
    try:
        import requests
        if action == 'history':
            days = request.args.get('days', 30)
            resp = requests.get(f"{invest_url}/api/market-sentiment", params={'action': 'history', 'days': days}, timeout=10)
        else:
            resp = requests.get(f"{invest_url}/api/market-sentiment", timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        logger.warning(f"市场情绪API不可用: {e}")
        return jsonify({'error': f'市场情绪服务不可用: {str(e)}'}), 503


@app.route('/api/portfolio')
def api_portfolio():
    """代理转发持仓数据API"""
    invest_url = os.environ.get('INVEST_API_URL', 'http://invest-backend:5000')
    try:
        import requests
        resp = requests.get(f"{invest_url}/api/portfolio", timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        logger.warning(f"持仓API不可用: {e}")
        return jsonify({'error': f'持仓服务不可用: {str(e)}'}), 503


@app.route('/api/invest-stats')
def api_invest_stats():
    """代理转发投资统计API"""
    invest_url = os.environ.get('INVEST_API_URL', 'http://invest-backend:5000')
    try:
        import requests
        resp = requests.get(f"{invest_url}/api/stats", timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        logger.warning(f"投资统计API不可用: {e}")
        return jsonify({'error': f'投资统计服务不可用: {str(e)}'}), 503


@app.route('/api/backtest-report')
def api_backtest_report():
    """获取回测报告"""
    data_base = Path(os.environ.get("DATA_BASE", "/app/data"))
    report_dir = data_base / "invest" / "backtest"
    if not report_dir.exists():
        report_dir = data_base / "invest" / "reports"
    if not report_dir.exists():
        return jsonify({"error": "回测报告目录不存在", "reports": []})

    reports = []
    for f in sorted(report_dir.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
        reports.append({
            "name": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })

    if not reports:
        return jsonify({"reports": [], "message": "暂无回测报告"})

    latest = report_dir / reports[0]["name"]
    content = ""
    try:
        content = latest.read_text(encoding="utf-8")[:10000]
    except Exception:
        content = "无法读取报告内容"

    return jsonify({"reports": reports, "latest_content": content})


@app.route('/api/funds', methods=['GET'])
def api_get_funds():
    """获取基金列表"""
    invest_url = os.environ.get('INVEST_API_URL', 'http://invest-backend:5000')
    try:
        import requests
        resp = requests.get(f"{invest_url}/api/portfolio", timeout=10)
        data = resp.json()
        holdings = data.get("holdings", data.get("funds", []))
        return jsonify({"funds": holdings})
    except Exception:
        config_path = Path(os.environ.get("INVEST_CONFIG", "/app/invest/config/user_config.yaml"))
        if not config_path.exists():
            config_path = Path(os.environ.get("INVEST_CONFIG", "/app/invest/config/default_config.yaml"))
        if config_path.exists():
            import yaml
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                return jsonify({"funds": config.get("funds", [])})
            except Exception:
                pass
        return jsonify({"funds": []})


@app.route('/api/funds', methods=['POST'])
def api_add_fund():
    """添加基金"""
    data = request.get_json(silent=True)
    if not data or not data.get('code'):
        return jsonify({'error': '缺少基金代码'}), 400

    config_path = Path(os.environ.get("INVEST_CONFIG", "/app/invest/config/user_config.yaml"))
    if not config_path.exists():
        config_path = Path(os.environ.get("INVEST_CONFIG", "/app/invest/config/default_config.yaml"))

    import yaml
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        funds = config.get("funds", [])
        for f in funds:
            if f.get("code") == data["code"]:
                return jsonify({'error': '基金已存在'}), 400

        funds.append({
            "code": data["code"],
            "name": data.get("name", ""),
            "monthly_invest": data.get("monthly_invest", 200),
            "enabled": True,
        })
        config["funds"] = funds

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        return jsonify({"success": True, "message": f"基金 {data['code']} 已添加"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/funds/<code>', methods=['DELETE'])
def api_delete_fund(code):
    """删除基金"""
    config_path = Path(os.environ.get("INVEST_CONFIG", "/app/invest/config/user_config.yaml"))
    if not config_path.exists():
        config_path = Path(os.environ.get("INVEST_CONFIG", "/app/invest/config/default_config.yaml"))

    import yaml
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        funds = config.get("funds", [])
        config["funds"] = [f for f in funds if f.get("code") != code]

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        return jsonify({"success": True, "message": f"基金 {code} 已删除"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
        .item-title a { color: #1a1a2e; text-decoration: none; }
        .item-title a:hover { color: #e94560; text-decoration: underline; }
        .portfolio-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px; }
        .portfolio-card { background: #f8f9fa; border-radius: 8px; padding: 15px; border-left: 4px solid #1a1a2e; }
        .portfolio-card.profit { border-left-color: #00cc44; }
        .portfolio-card.loss { border-left-color: #ff4444; }
        .portfolio-card .fund-name { font-weight: 600; font-size: 15px; }
        .portfolio-card .fund-detail { font-size: 13px; color: #666; margin-top: 8px; line-height: 1.6; }
        .portfolio-card .pnl { font-size: 20px; font-weight: bold; margin-top: 5px; }
        .pnl.positive { color: #00cc44; }
        .pnl.negative { color: #ff4444; }
        .backtest-content { background: #f8f9fa; border-radius: 6px; padding: 15px; font-family: monospace; font-size: 13px; white-space: pre-wrap; max-height: 400px; overflow-y: auto; line-height: 1.5; }
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
            <h2>持仓日报</h2>
            <div id="portfolio-summary" style="margin-bottom: 15px; font-size: 14px; color: #666;">加载中...</div>
            <div id="portfolio-cards" class="portfolio-grid"><div class="empty">加载中...</div></div>
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

        <div class="section">
            <h2>回测报告</h2>
            <div id="backtest-info"><div class="empty">加载中...</div></div>
        </div>

        <div class="section">
            <h2>基金管理</h2>
            <div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;">
                <input type="text" id="fundCode" placeholder="基金代码 如 110011" style="width: 120px; padding: 8px; border: 1px solid #ddd; border-radius: 6px;">
                <input type="text" id="fundName" placeholder="基金名称（可选）" style="width: 180px; padding: 8px; border: 1px solid #ddd; border-radius: 6px;">
                <input type="number" id="fundAmount" placeholder="每月定投" value="200" style="width: 100px; padding: 8px; border: 1px solid #ddd; border-radius: 6px;">
                <button class="refresh-btn" onclick="addFund()">添加基金</button>
            </div>
            <div id="fund-list"><div class="empty">加载中...</div></div>
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
                    `<div class="item"><div class="item-title">${item.url ? `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>` : item.title}</div><div class="item-meta"><span class="badge badge-source">${item.source}</span> ${item.date}</div></div>`
                );

                renderList('analyse-high', data.analyse.high_score, item =>
                    `<div class="item"><div class="item-title">${item.title}</div><div class="item-meta"><span class="badge badge-score">评分 ${item.score}</span> ${item.category}</div></div>`
                );

                renderList('job-high', data.jobs.high_score, item =>
                    `<div class="item"><div class="item-title">${item.url ? `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>` : item.title} - ${item.company}</div><div class="item-meta"><span class="badge badge-score">匹配度 ${item.score}%</span></div></div>`
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
                if (typeof Chart === 'undefined') {
                    console.log('Chart.js 尚未加载，跳过图表渲染');
                    return;
                }
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
                        `<div class="item"><div class="item-title">${item.url ? `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>` : item.title}</div><div class="item-meta"><span class="badge badge-source">${item.source}</span> ${item.date}</div></div>`
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
                    <div class="item-title" style="font-size:15px; line-height:1.8;">${(data.answer || '').replace(/\\n/g, '<br>')}</div>
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

        async function loadPortfolio() {
            try {
                const resp = await fetchWithTimeout('/api/portfolio', {}, 8000);
                if (!resp.ok) return;
                const data = await resp.json();
                if (data.error) {
                    document.getElementById('portfolio-summary').textContent = '持仓服务暂不可用';
                    document.getElementById('portfolio-cards').innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                const holdings = data.holdings || data.funds || [];
                const summary = data.summary || {};
                const summaryEl = document.getElementById('portfolio-summary');
                const cardsEl = document.getElementById('portfolio-cards');

                if (summary.total_assets !== undefined) {
                    const pnlClass = (summary.total_pnl || 0) >= 0 ? 'positive' : 'negative';
                    const pnlSign = (summary.total_pnl || 0) >= 0 ? '+' : '';
                    summaryEl.innerHTML = `总资产: <b>¥${(summary.total_assets || 0).toLocaleString()}</b> | 总盈亏: <span class="pnl ${pnlClass}">${pnlSign}¥${(summary.total_pnl || 0).toLocaleString()}</span> (${pnlSign}${(summary.total_pnl_pct || 0).toFixed(2)}%)`;
                }

                if (!holdings || holdings.length === 0) {
                    cardsEl.innerHTML = '<div class="empty">暂无持仓数据</div>';
                    return;
                }

                cardsEl.innerHTML = holdings.map(h => {
                    const pnl = h.pnl || h.profit_loss || 0;
                    const pnlPct = h.pnl_pct || h.profit_loss_pct || 0;
                    const isProfit = pnl >= 0;
                    const sign = isProfit ? '+' : '';
                    return `<div class="portfolio-card ${isProfit ? 'profit' : 'loss'}">
                        <div class="fund-name">${h.fund_name || h.name || '--'}</div>
                        <div class="fund-detail">
                            代码: ${h.fund_code || h.code || '--'} | 持有: ${h.shares || '--'}份<br>
                            成本: ¥${(h.cost || h.avg_cost || 0).toFixed(4)} | 现价: ¥${(h.nav || h.current_nav || h.price || 0).toFixed(4)}
                        </div>
                        <div class="pnl ${isProfit ? 'positive' : 'negative'}">${sign}¥${pnl.toFixed(2)} (${sign}${pnlPct.toFixed(2)}%)</div>
                    </div>`;
                }).join('');

                loadInvestAlerts();
            } catch (e) {
                console.log('持仓数据加载跳过:', e.message);
                document.getElementById('portfolio-summary').textContent = '持仓服务暂不可用';
            }
        }

        async function loadInvestAlerts() {
            try {
                const resp = await fetchWithTimeout('/api/invest-stats', {}, 5000);
                if (!resp.ok) return;
                const data = await resp.json();
                if (data.alerts && data.alerts.length > 0) {
                    renderList('invest-alerts', data.alerts, item =>
                        `<div class="item"><div class="item-title">${item.fund_name || ''}</div><div class="item-meta"><span class="badge badge-hot">${item.alert_type || '预警'}</span> ${item.message || ''}</div></div>`
                    );
                }
            } catch (e) {
                console.log('投资预警加载跳过:', e.message);
            }
        }

        async function loadBacktest() {
            try {
                const resp = await fetch('/api/backtest-report');
                const data = await resp.json();
                const el = document.getElementById('backtest-info');

                if (data.error && (!data.reports || data.reports.length === 0)) {
                    el.innerHTML = `<div class="empty">${data.error || data.message || '暂无回测报告'}</div>`;
                    return;
                }

                let html = '';
                if (data.reports && data.reports.length > 0) {
                    html += `<div style="margin-bottom:10px;">共 ${data.reports.length} 份报告</div>`;
                    data.reports.forEach(r => {
                        html += `<div class="item"><div class="item-title">${r.name}</div><div class="item-meta">${r.size_kb} KB | ${r.modified}</div></div>`;
                    });
                }
                if (data.latest_content) {
                    html += `<div style="margin-top:15px;"><div style="font-weight:500; margin-bottom:8px;">最新报告内容：</div><div class="backtest-content">${data.latest_content}</div></div>`;
                }
                el.innerHTML = html || '<div class="empty">暂无回测报告</div>';
            } catch (e) {
                console.log('回测报告加载跳过:', e.message);
            }
        }

        async function loadFunds() {
            try {
                const resp = await fetch('/api/funds');
                const data = await resp.json();
                const el = document.getElementById('fund-list');
                const funds = data.funds || [];

                if (funds.length === 0) {
                    el.innerHTML = '<div class="empty">暂无基金，请添加</div>';
                    return;
                }

                el.innerHTML = funds.map(f => {
                    const code = f.fund_code || f.code || '';
                    const name = f.fund_name || f.name || '--';
                    const amount = f.monthly_invest || '--';
                    const nav = f.nav || f.current_nav || f.price || '';
                    const pnl = f.pnl || f.profit || 0;
                    const pnlPct = f.pnl_pct || f.profit_rate || 0;
                    const pnlClass = pnl >= 0 ? 'positive' : 'negative';
                    const sign = pnl >= 0 ? '+' : '';
                    return `<div class="portfolio-card ${pnl >= 0 ? 'profit' : 'loss'}" style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <div class="fund-name">${name}</div>
                            <div class="fund-detail">代码: ${code} | 定投: ¥${amount}/月${nav ? ' | 净值: ¥' + Number(nav).toFixed(4) : ''}</div>
                            ${pnl ? `<div class="pnl ${pnlClass}" style="font-size:16px;">${sign}¥${pnl.toFixed(2)} (${sign}${pnlPct.toFixed(2)}%)</div>` : ''}
                        </div>
                        <button onclick="deleteFund('${code}')" style="background:#ff4444; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer; font-size:12px;">删除</button>
                    </div>`;
                }).join('');
            } catch (e) {
                console.log('基金列表加载失败:', e.message);
            }
        }

        async function addFund() {
            const code = document.getElementById('fundCode').value.trim();
            const name = document.getElementById('fundName').value.trim();
            const amount = parseInt(document.getElementById('fundAmount').value) || 200;

            if (!code) {
                alert('请输入基金代码');
                return;
            }

            try {
                const resp = await fetch('/api/funds', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({code, name, monthly_invest: amount})
                });
                const data = await resp.json();
                if (data.error) {
                    alert(data.error);
                } else {
                    alert(data.message || '添加成功');
                    document.getElementById('fundCode').value = '';
                    document.getElementById('fundName').value = '';
                    loadFunds();
                }
            } catch (e) {
                alert('添加失败: ' + e.message);
            }
        }

        async function deleteFund(code) {
            if (!confirm(`确定删除基金 ${code}？`)) return;
            try {
                const resp = await fetch(`/api/funds/${code}`, {method: 'DELETE'});
                const data = await resp.json();
                if (data.error) {
                    alert(data.error);
                } else {
                    alert(data.message || '删除成功');
                    loadFunds();
                }
            } catch (e) {
                alert('删除失败: ' + e.message);
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
                if (typeof Chart === 'undefined') {
                    console.log('Chart.js 尚未加载，跳过情绪图表');
                    return;
                }

                const resp = await fetchWithTimeout('/api/market-sentiment', {}, 5000);
                if (!resp.ok) return;
                const data = await resp.json();
                if (data.error) { console.log('情绪数据不可用:', data.error); return; }

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

                const histResp = await fetchWithTimeout('/api/market-sentiment?action=history&days=30', {}, 5000);
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
        loadPortfolio();
        loadBacktest();
        loadFunds();
        setInterval(loadData, 60000);
        setInterval(loadSentiment, 300000);
        setInterval(loadPortfolio, 300000);

        var chartUrls = [
            'https://cdn.bootcdn.net/ajax/libs/Chart.js/4.4.7/chart.umd.min.js',
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.7/chart.umd.min.js'
        ];
        function loadChartScript(idx) {
            if (idx >= chartUrls.length) return;
            var s = document.createElement('script');
            s.src = chartUrls[idx];
            s.onload = function() {
                console.log('Chart.js 加载成功: ' + chartUrls[idx]);
                loadTrend();
                loadSentiment();
            };
            s.onerror = function() {
                console.log('Chart.js 加载失败: ' + chartUrls[idx] + '，尝试下一个');
                loadChartScript(idx + 1);
            };
            document.body.appendChild(s);
        }
        loadChartScript(0);
    </script>
</body>
</html>"""


@app.route('/')
def dashboard():
    """Dashboard 主页"""
    return DASHBOARD_HTML


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

    # 分析数据库（兼容 analyzer.db 和 analyzed.db）
    analyse_default = os.environ.get("ANALYSE_DB", str(data_base / "knowledge_base" / "analyzed.db"))
    DB_PATHS["analyse"] = resolve_db_path("analyse", analyse_default, [
        str(data_base / "knowledge_base" / "analyzer.db"),
        str(data_base / "knowledge_base" / "analyzed.db"),
        str(data_base / "shared" / "data" / "analyzer.db"),
    ])

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
