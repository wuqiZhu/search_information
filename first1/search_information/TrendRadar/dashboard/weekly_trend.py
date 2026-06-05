#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrendRadar 每周趋势分析器
分析过去一周的信号数据，生成趋势报告
"""

import os
import sys
import json
import glob
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, Counter


def load_signals(signals_dir: str, days: int = 7) -> list:
    """加载指定天数内的信号"""
    signals = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    if not os.path.exists(signals_dir):
        return signals
    
    for filepath in glob.glob(os.path.join(signals_dir, '*.json')):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                signal = json.load(f)
            
            timestamp = signal.get('timestamp', '')
            if timestamp:
                try:
                    signal_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    if signal_date >= cutoff_date:
                        signals.append(signal)
                except:
                    pass
        except Exception as e:
            print(f"读取信号文件失败 {filepath}: {e}")
    
    return signals


def analyze_trends(signals: list) -> dict:
    """分析信号趋势"""
    trends = {
        'total_signals': len(signals),
        'date_range': {
            'start': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
            'end': datetime.now().strftime('%Y-%m-%d')
        },
        'by_source': defaultdict(int),
        'by_keyword': defaultdict(int),
        'by_date': defaultdict(int),
        'top_keywords': [],
        'top_sources': [],
        'keyword_trends': {},
        'source_trends': {}
    }
    
    # 统计来源
    for signal in signals:
        source = signal.get('source', '未知')
        trends['by_source'][source] += 1
        
        # 统计关键词
        for keyword in signal.get('keywords', []):
            trends['by_keyword'][keyword] += 1
        
        # 统计日期
        timestamp = signal.get('timestamp', '')
        if timestamp:
            try:
                date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date()
                trends['by_date'][date.isoformat()] += 1
            except:
                pass
    
    # 排序
    trends['top_keywords'] = sorted(trends['by_keyword'].items(), key=lambda x: -x[1])[:10]
    trends['top_sources'] = sorted(trends['by_source'].items(), key=lambda x: -x[1])[:5]
    
    # 计算关键词趋势（按天）
    for signal in signals:
        timestamp = signal.get('timestamp', '')
        if timestamp:
            try:
                date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date().isoformat()
                for keyword in signal.get('keywords', []):
                    if keyword not in trends['keyword_trends']:
                        trends['keyword_trends'][keyword] = defaultdict(int)
                    trends['keyword_trends'][keyword][date] += 1
            except:
                pass
    
    # 计算来源趋势（按天）
    for signal in signals:
        timestamp = signal.get('timestamp', '')
        if timestamp:
            try:
                date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date().isoformat()
                source = signal.get('source', '未知')
                if source not in trends['source_trends']:
                    trends['source_trends'][source] = defaultdict(int)
                trends['source_trends'][source][date] += 1
            except:
                pass
    
    return trends


def generate_trend_report(trends: dict, output_file: str):
    """生成趋势报告"""
    now = datetime.now()
    
    # 生成热门关键词云数据
    keyword_cloud_data = []
    for keyword, count in trends['top_keywords']:
        keyword_cloud_data.append({
            'keyword': keyword,
            'count': count,
            'weight': min(count * 10, 100)
        })
    
    # 生成每日趋势数据
    daily_trend_data = []
    for i in range(7):
        date = (now - timedelta(days=6-i)).date()
        date_str = date.isoformat()
        count = trends['by_date'].get(date_str, 0)
        daily_trend_data.append({
            'date': date_str,
            'count': count
        })
    
    # 生成来源分布数据
    source_data = []
    for source, count in trends['top_sources']:
        source_data.append({
            'source': source,
            'count': count,
            'percentage': round(count / trends['total_signals'] * 100, 1) if trends['total_signals'] > 0 else 0
        })
    
    # 构建报告数据
    report = {
        'generated_at': now.isoformat(),
        'date_range': trends['date_range'],
        'summary': {
            'total_signals': trends['total_signals'],
            'unique_keywords': len(trends['by_keyword']),
            'unique_sources': len(trends['by_source']),
            'avg_daily_signals': round(trends['total_signals'] / 7, 1)
        },
        'top_keywords': [{'keyword': k, 'count': c} for k, c in trends['top_keywords']],
        'top_sources': [{'source': s, 'count': c} for s, c in trends['top_sources']],
        'daily_trend': daily_trend_data,
        'keyword_cloud': keyword_cloud_data,
        'source_distribution': source_data
    }
    
    # 保存 JSON 报告
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"趋势报告已生成: {output_file}")
    return report


def generate_markdown_report(report: dict, output_file: str):
    """生成 Markdown 格式的趋势报告"""
    now = datetime.now()
    
    md_content = f"""# 📊 TrendRadar 每周趋势报告

**生成时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}  
**统计周期**: {report['date_range']['start']} 至 {report['date_range']['end']}

---

## 📈 本周概览

| 指标 | 数值 |
|------|------|
| 总信号数 | {report['summary']['total_signals']} |
| 独立关键词 | {report['summary']['unique_keywords']} |
| 信号来源数 | {report['summary']['unique_sources']} |
| 日均信号 | {report['summary']['avg_daily_signals']} |

---

## 🔥 热门关键词 TOP 10

| 排名 | 关键词 | 出现次数 |
|------|--------|----------|
"""
    
    for i, kw in enumerate(report['top_keywords'][:10], 1):
        md_content += f"| {i} | {kw['keyword']} | {kw['count']} |\n"
    
    md_content += f"""
---

## 📍 热门来源 TOP 5

| 排名 | 来源 | 信号数 | 占比 |
|------|------|--------|------|
"""
    
    for i, source in enumerate(report['top_sources'][:5], 1):
        percentage = round(source['count'] / report['summary']['total_signals'] * 100, 1) if report['summary']['total_signals'] > 0 else 0
        md_content += f"| {i} | {source['source']} | {source['count']} | {percentage}% |\n"
    
    md_content += f"""
---

## 📅 每日信号趋势

| 日期 | 信号数 | 趋势 |
|------|--------|------|
"""
    
    for day in report['daily_trend']:
        trend_icon = "📈" if day['count'] > report['summary']['avg_daily_signals'] else "📉" if day['count'] < report['summary']['avg_daily_signals'] else "➡️"
        md_content += f"| {day['date']} | {day['count']} | {trend_icon} |\n"
    
    md_content += f"""
---

## 🔍 趋势分析

### 关键词热度变化
"""
    
    # 分析关键词趋势
    rising_keywords = []
    for kw_data in report['top_keywords'][:5]:
        keyword = kw_data['keyword']
        # 简单趋势分析：比较后3天和前3天
        recent_count = sum(1 for day in report['daily_trend'][-3:] for _ in range(day['count']))
        earlier_count = sum(1 for day in report['daily_trend'][:3] for _ in range(day['count']))
        if recent_count > earlier_count * 1.2:
            rising_keywords.append(keyword)
    
    if rising_keywords:
        md_content += f"- 📈 **上升趋势**: {', '.join(rising_keywords)}\n"
    else:
        md_content += "- ➡️ **整体稳定**: 关键词热度无明显变化\n"
    
    md_content += f"""
### 来源活跃度
"""
    
    # 分析来源趋势
    active_sources = [s['source'] for s in report['top_sources'][:3]]
    md_content += f"- 🏆 **最活跃来源**: {', '.join(active_sources)}\n"
    
    md_content += f"""
---

## 💡 建议

1. **关注上升趋势关键词**: 持续跟踪热度上升的技术话题
2. **优化信号源**: 考虑增加活跃来源的监控频率
3. **调整关键词**: 根据趋势变化调整监控关键词

---

*此报告由 TrendRadar 自动生成*
"""
    
    # 保存 Markdown 报告
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"Markdown 报告已生成: {output_file}")


def main():
    """主函数"""
    # 获取项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    trendradar_dir = os.path.dirname(script_dir)
    
    signals_dir = os.path.join(trendradar_dir, 'data', 'signals')
    output_json = os.path.join(script_dir, 'weekly_trend.json')
    output_md = os.path.join(script_dir, 'weekly_trend.md')
    
    print("=" * 50)
    print("TrendRadar 每周趋势分析")
    print("=" * 50)
    
    # 加载信号
    signals = load_signals(signals_dir, days=7)
    print(f"加载了 {len(signals)} 个信号")
    
    if not signals:
        print("没有找到信号数据，跳过分析")
        return
    
    # 分析趋势
    trends = analyze_trends(signals)
    
    # 生成报告
    report = generate_trend_report(trends, output_json)
    generate_markdown_report(report, output_md)
    
    print("=" * 50)
    print("分析完成！")
    print(f"JSON 报告: {output_json}")
    print(f"Markdown 报告: {output_md}")
    print("=" * 50)


if __name__ == '__main__':
    main()
