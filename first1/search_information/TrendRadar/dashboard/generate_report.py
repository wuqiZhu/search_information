#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrendRadar 仪表盘生成器
生成 HTML 格式的运行报告，包含信号统计、源健康状态、AI成本追踪等
"""

import os
import sys
import json
import glob
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, Counter
import html


def load_json_file(filepath: str) -> dict:
    """加载 JSON 文件"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"加载文件失败 {filepath}: {e}")
    return {}


def get_signal_stats(signals_dir: str) -> dict:
    """获取信号统计信息"""
    stats = {
        'total': 0,
        'today': 0,
        'this_week': 0,
        'by_source': defaultdict(int),
        'by_keyword': defaultdict(int),
        'by_date': defaultdict(int)
    }
    
    if not os.path.exists(signals_dir):
        return stats
    
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    
    for filepath in glob.glob(os.path.join(signals_dir, '*.json')):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                signal = json.load(f)
            
            stats['total'] += 1
            
            # 按来源统计
            source = signal.get('source', '未知')
            stats['by_source'][source] += 1
            
            # 按关键词统计
            for keyword in signal.get('keywords', []):
                stats['by_keyword'][keyword] += 1
            
            # 按日期统计
            timestamp = signal.get('timestamp', '')
            if timestamp:
                try:
                    date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date()
                    stats['by_date'][date.isoformat()] += 1
                    
                    if date == today:
                        stats['today'] += 1
                    if date >= week_ago:
                        stats['this_week'] += 1
                except:
                    pass
        except Exception as e:
            print(f"读取信号文件失败 {filepath}: {e}")
    
    return stats


def get_health_status(data_dir: str) -> dict:
    """获取健康状态"""
    health_file = os.path.join(data_dir, 'health_report.json')
    return load_json_file(health_file)


def get_heartbeat(data_dir: str) -> dict:
    """获取心跳状态"""
    heartbeat_file = os.path.join(data_dir, 'heartbeat.json')
    return load_json_file(heartbeat_file)


def get_cost_tracker(analyzer_dir: str) -> dict:
    """获取 AI 成本追踪"""
    cost_file = os.path.join(analyzer_dir, 'data', 'ai_cost_tracker.json')
    return load_json_file(cost_file)


def get_dead_letter_count(data_dir: str) -> int:
    """获取死信队列数量"""
    dead_letter_file = os.path.join(data_dir, 'dead_letter', 'dead_letter.json')
    try:
        if os.path.exists(dead_letter_file):
            with open(dead_letter_file, 'r', encoding='utf-8') as f:
                letters = json.load(f)
            return len(letters)
    except:
        pass
    return 0


def generate_html_report(data_dir: str, analyzer_dir: str, output_file: str):
    """生成 HTML 报告"""
    # 获取数据
    signals_dir = os.path.join(data_dir, 'signals')
    signal_stats = get_signal_stats(signals_dir)
    health_status = get_health_status(data_dir)
    heartbeat = get_heartbeat(data_dir)
    cost_tracker = get_cost_tracker(analyzer_dir)
    dead_letter_count = get_dead_letter_count(data_dir)
    
    # 生成当前时间
    now = datetime.now()
    
    # 构建 HTML
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrendRadar 仪表盘</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        .header h1 {{
            color: #333;
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .header .subtitle {{
            color: #666;
            font-size: 1.1em;
        }}
        .header .update-time {{
            color: #999;
            font-size: 0.9em;
            margin-top: 10px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s ease;
        }}
        .card:hover {{
            transform: translateY(-5px);
        }}
        .card h2 {{
            color: #333;
            font-size: 1.5em;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .card h2 .icon {{
            font-size: 1.2em;
        }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }}
        .stat-item {{
            text-align: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
        }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-label {{
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        .status-badge {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }}
        .status-healthy {{
            background: #d4edda;
            color: #155724;
        }}
        .status-degraded {{
            background: #fff3cd;
            color: #856404;
        }}
        .status-critical {{
            background: #f8d7da;
            color: #721c24;
        }}
        .status-unknown {{
            background: #e2e3e5;
            color: #383d41;
        }}
        .source-list {{
            list-style: none;
        }}
        .source-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }}
        .source-item:last-child {{
            border-bottom: none;
        }}
        .source-name {{
            font-weight: 500;
        }}
        .keyword-cloud {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .keyword-tag {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
        }}
        .progress-bar {{
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 10px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 10px;
            transition: width 0.3s ease;
        }}
        .alert-box {{
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
        }}
        .alert-warning {{
            background: #fff3cd;
            border: 1px solid #ffc107;
            color: #856404;
        }}
        .alert-success {{
            background: #d4edda;
            border: 1px solid #28a745;
            color: #155724;
        }}
        .footer {{
            text-align: center;
            color: white;
            padding: 20px;
            font-size: 0.9em;
        }}
        @media (max-width: 768px) {{
            .grid {{
                grid-template-columns: 1fr;
            }}
            .stat-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📡 TrendRadar 仪表盘</h1>
            <div class="subtitle">嵌入式Linux技术信号监控系统</div>
            <div class="update-time">更新时间: {now.strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        
        <div class="grid">
            <!-- 信号统计卡片 -->
            <div class="card">
                <h2><span class="icon">📊</span> 信号统计</h2>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-value">{signal_stats['total']}</div>
                        <div class="stat-label">总信号数</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{signal_stats['today']}</div>
                        <div class="stat-label">今日新增</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{signal_stats['this_week']}</div>
                        <div class="stat-label">本周新增</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{dead_letter_count}</div>
                        <div class="stat-label">死信队列</div>
                    </div>
                </div>
            </div>
            
            <!-- 系统状态卡片 -->
            <div class="card">
                <h2><span class="icon">💓</span> 系统状态</h2>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-value">{heartbeat.get('processed_count', 0)}</div>
                        <div class="stat-label">已处理信号</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{heartbeat.get('pending_signals_count', 0)}</div>
                        <div class="stat-label">待处理信号</div>
                    </div>
                </div>
                <div class="alert-box {'alert-success' if heartbeat.get('status') == 'running' else 'alert-warning'}">
                    系统状态: {'运行中' if heartbeat.get('status') == 'running' else '未知'}
                </div>
            </div>
            
            <!-- 源健康状态卡片 -->
            <div class="card">
                <h2><span class="icon">🏥</span> 源健康状态</h2>
                {'<span class="status-badge status-' + health_status.get('overall_status', 'unknown') + '">' + health_status.get('overall_status', '未知').upper() + '</span>' if health_status else '<span class="status-badge status-unknown">未检测</span>'}
                {'<p style="margin-top: 15px; color: #666;">失败源: ' + str(health_status.get('failed_count', 0)) + ' 个</p>' if health_status else ''}
                {'<p style="color: #666;">检测时间: ' + health_status.get('timestamp', '未知')[:19] + '</p>' if health_status else ''}
            </div>
            
            <!-- AI成本追踪卡片 -->
            <div class="card">
                <h2><span class="icon">💰</span> AI成本追踪</h2>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-value">{cost_tracker.get('daily_calls', 0)}</div>
                        <div class="stat-label">今日调用</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${cost_tracker.get('daily_cost', 0):.2f}</div>
                        <div class="stat-label">今日费用</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{cost_tracker.get('monthly_calls', 0)}</div>
                        <div class="stat-label">本月调用</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${cost_tracker.get('monthly_cost', 0):.2f}</div>
                        <div class="stat-label">本月费用</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 来源分布卡片 -->
        <div class="card" style="margin-bottom: 20px;">
            <h2><span class="icon">📍</span> 信号来源分布</h2>
            <ul class="source-list">
                {"".join(f'<li class="source-item"><span class="source-name">{html.escape(source)}</span><span>{count} 条</span></li>' for source, count in sorted(signal_stats['by_source'].items(), key=lambda x: -x[1])[:10])}
            </ul>
        </div>
        
        <!-- 热门关键词卡片 -->
        <div class="card" style="margin-bottom: 20px;">
            <h2><span class="icon">🔥</span> 热门关键词</h2>
            <div class="keyword-cloud">
                {"".join(f'<span class="keyword-tag">{html.escape(keyword)} ({count})</span>' for keyword, count in sorted(signal_stats['by_keyword'].items(), key=lambda x: -x[1])[:15])}
            </div>
        </div>
        
        <!-- 每日信号趋势 -->
        <div class="card" style="margin-bottom: 20px;">
            <h2><span class="icon">📈</span> 每日信号趋势（近7天）</h2>
            <div style="display: flex; align-items: flex-end; height: 200px; gap: 10px; padding: 20px 0;">
                {"".join(f'<div style="flex: 1; display: flex; flex-direction: column; align-items: center;"><div style="width: 100%; background: linear-gradient(180deg, #667eea, #764ba2); border-radius: 5px 5px 0 0; height: {max(20, count * 30)}px;"></div><div style="font-size: 0.8em; color: #666; margin-top: 5px;">{date[-5:]}</div><div style="font-size: 0.9em; font-weight: bold;">{count}</div></div>' for date, count in sorted(signal_stats['by_date'].items())[-7:])}
            </div>
        </div>
        
        <div class="footer">
            TrendRadar - 嵌入式Linux技术信号监控系统 | 自动生成于 {now.strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>"""
    
    # 保存 HTML 文件
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"仪表盘报告已生成: {output_file}")
    return output_file


def main():
    """主函数"""
    # 获取项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    trendradar_dir = os.path.dirname(script_dir)
    project_dir = os.path.dirname(trendradar_dir)
    
    data_dir = os.path.join(trendradar_dir, 'data')
    analyzer_dir = os.path.join(project_dir, 'analyzer')
    output_file = os.path.join(script_dir, 'report.html')
    
    print("=" * 50)
    print("TrendRadar 仪表盘生成器")
    print("=" * 50)
    
    generate_html_report(data_dir, analyzer_dir, output_file)
    
    print("=" * 50)
    print("生成完成！")
    print(f"报告位置: {output_file}")
    print("=" * 50)


if __name__ == '__main__':
    main()
