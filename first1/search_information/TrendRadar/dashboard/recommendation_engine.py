#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrendRadar 个性化推荐引擎
基于用户反馈和历史行为，生成个性化推荐
"""

import os
import sys
import json
import glob
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, Counter


def load_feedback() -> dict:
    """加载用户反馈数据"""
    feedback_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'user_feedback.json')
    if os.path.exists(feedback_file):
        try:
            with open(feedback_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'signals': {}, 'keywords': {}, 'sources': {}}


def load_signals(signals_dir: str, days: int = 30) -> list:
    """加载信号数据"""
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
        except:
            pass
    
    return signals


def calculate_keyword_weights(feedback: dict) -> dict:
    """计算关键词权重"""
    weights = {}
    
    for keyword, stats in feedback.get('keywords', {}).items():
        favorite = stats.get('favorite', 0)
        ignore = stats.get('ignore', 0)
        click = stats.get('click', 0)
        
        # 计算权重：收藏+1，忽略-1，点击+0.5
        weight = (favorite * 1.0) - (ignore * 1.0) + (click * 0.5)
        weights[keyword] = weight
    
    return weights


def calculate_source_weights(feedback: dict) -> dict:
    """计算来源权重"""
    weights = {}
    
    for source, stats in feedback.get('sources', {}).items():
        favorite = stats.get('favorite', 0)
        ignore = stats.get('ignore', 0)
        click = stats.get('click', 0)
        
        # 计算权重
        weight = (favorite * 1.0) - (ignore * 1.0) + (click * 0.5)
        weights[source] = weight
    
    return weights


def calculate_signal_score(signal: dict, keyword_weights: dict, source_weights: dict) -> float:
    """计算信号的个性化分数"""
    base_score = signal.get('relevance_score', 0)
    
    # 关键词权重加成
    keyword_bonus = 0
    for keyword in signal.get('keywords', []):
        if keyword in keyword_weights:
            keyword_bonus += keyword_weights[keyword] * 0.1
    
    # 来源权重加成
    source = signal.get('source', '')
    source_bonus = source_weights.get(source, 0) * 0.05
    
    # 最终分数
    final_score = base_score + keyword_bonus + source_bonus
    
    # 归一化到 0-1
    return max(0, min(1, final_score))


def generate_recommendations(signals: list, feedback: dict, top_n: int = 10) -> list:
    """生成个性化推荐"""
    # 计算权重
    keyword_weights = calculate_keyword_weights(feedback)
    source_weights = calculate_source_weights(feedback)
    
    # 计算每个信号的个性化分数
    scored_signals = []
    for signal in signals:
        score = calculate_signal_score(signal, keyword_weights, source_weights)
        scored_signals.append({
            'signal': signal,
            'personalized_score': score,
            'keyword_weights': {kw: keyword_weights.get(kw, 0) for kw in signal.get('keywords', [])},
            'source_weight': source_weights.get(signal.get('source', ''), 0)
        })
    
    # 按个性化分数排序
    scored_signals.sort(key=lambda x: x['personalized_score'], reverse=True)
    
    # 返回 top N
    return scored_signals[:top_n]


def analyze_user_preferences(feedback: dict) -> dict:
    """分析用户偏好"""
    preferences = {
        'favorite_keywords': [],
        'ignore_keywords': [],
        'favorite_sources': [],
        'ignore_sources': [],
        'interest_patterns': []
    }
    
    # 分析关键词偏好
    for keyword, stats in feedback.get('keywords', {}).items():
        favorite = stats.get('favorite', 0)
        ignore = stats.get('ignore', 0)
        
        if favorite > ignore:
            preferences['favorite_keywords'].append({
                'keyword': keyword,
                'score': favorite - ignore,
                'total': favorite + ignore
            })
        elif ignore > favorite:
            preferences['ignore_keywords'].append({
                'keyword': keyword,
                'score': ignore - favorite,
                'total': favorite + ignore
            })
    
    # 分析来源偏好
    for source, stats in feedback.get('sources', {}).items():
        favorite = stats.get('favorite', 0)
        ignore = stats.get('ignore', 0)
        
        if favorite > ignore:
            preferences['favorite_sources'].append({
                'source': source,
                'score': favorite - ignore,
                'total': favorite + ignore
            })
        elif ignore > favorite:
            preferences['ignore_sources'].append({
                'source': source,
                'score': ignore - favorite,
                'total': favorite + ignore
            })
    
    # 排序
    preferences['favorite_keywords'].sort(key=lambda x: x['score'], reverse=True)
    preferences['ignore_keywords'].sort(key=lambda x: x['score'], reverse=True)
    preferences['favorite_sources'].sort(key=lambda x: x['score'], reverse=True)
    preferences['ignore_sources'].sort(key=lambda x: x['score'], reverse=True)
    
    return preferences


def generate_recommendation_report(recommendations: list, preferences: dict, output_file: str):
    """生成推荐报告"""
    now = datetime.now()
    
    report = {
        'generated_at': now.isoformat(),
        'user_preferences': preferences,
        'recommendations': []
    }
    
    for rec in recommendations:
        signal = rec['signal']
        report['recommendations'].append({
            'title': signal.get('title', ''),
            'source': signal.get('source', ''),
            'url': signal.get('url', ''),
            'keywords': signal.get('keywords', []),
            'original_score': signal.get('relevance_score', 0),
            'personalized_score': rec['personalized_score'],
            'keyword_weights': rec['keyword_weights'],
            'source_weight': rec['source_weight']
        })
    
    # 保存报告
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return report


def generate_markdown_report(report: dict, output_file: str):
    """生成 Markdown 格式的推荐报告"""
    now = datetime.now()
    
    md_content = f"""# 🎯 TrendRadar 个性化推荐报告

**生成时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}

---

## 📊 用户偏好分析

### 🔥 收藏关键词
"""
    
    for kw in report['user_preferences']['favorite_keywords'][:10]:
        md_content += f"- **{kw['keyword']}** (得分: {kw['score']}, 总数: {kw['total']})\n"
    
    md_content += f"""
### 🚫 忽略关键词
"""
    
    for kw in report['user_preferences']['ignore_keywords'][:10]:
        md_content += f"- {kw['keyword']} (得分: {kw['score']}, 总数: {kw['total']})\n"
    
    md_content += f"""
### 📍 收藏来源
"""
    
    for source in report['user_preferences']['favorite_sources'][:5]:
        md_content += f"- **{source['source']}** (得分: {source['score']})\n"
    
    md_content += f"""
### 🚫 忽略来源
"""
    
    for source in report['user_preferences']['ignore_sources'][:5]:
        md_content += f"- {source['source']} (得分: {source['score']})\n"
    
    md_content += f"""
---

## 🎯 个性化推荐 TOP 10

"""
    
    for i, rec in enumerate(report['recommendations'][:10], 1):
        md_content += f"""### {i}. {rec['title'][:60]}

- **来源**: {rec['source']}
- **关键词**: {', '.join(rec['keywords'][:3])}
- **原始分数**: {rec['original_score']:.2f}
- **个性化分数**: {rec['personalized_score']:.2f}
- **链接**: [{rec['url'][:50]}...]({rec['url']})

"""
    
    md_content += f"""
---

## 💡 推荐理由

基于您的反馈行为，系统自动调整了信号权重：
- 收藏的关键词和来源会获得更高权重
- 忽略的关键词和来源会获得更低权重
- 个性化分数 = 原始分数 + 关键词加成 + 来源加成

---

*此报告由 TrendRadar 推荐引擎自动生成*
"""
    
    # 保存报告
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(md_content)


def main():
    """主函数"""
    # 获取项目路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    trendradar_dir = os.path.dirname(script_dir)
    
    signals_dir = os.path.join(trendradar_dir, 'data', 'signals')
    output_json = os.path.join(script_dir, 'recommendations.json')
    output_md = os.path.join(script_dir, 'recommendations.md')
    
    print("=" * 50)
    print("TrendRadar 个性化推荐引擎")
    print("=" * 50)
    
    # 加载数据
    feedback = load_feedback()
    signals = load_signals(signals_dir, days=30)
    
    print(f"加载了 {len(signals)} 个信号")
    print(f"用户反馈: {len(feedback.get('signals', {}))} 个信号")
    
    if not signals:
        print("没有信号数据，跳过推荐")
        return
    
    # 分析用户偏好
    preferences = analyze_user_preferences(feedback)
    print(f"收藏关键词: {len(preferences['favorite_keywords'])} 个")
    print(f"忽略关键词: {len(preferences['ignore_keywords'])} 个")
    
    # 生成推荐
    recommendations = generate_recommendations(signals, feedback, top_n=10)
    
    # 生成报告
    report = generate_recommendation_report(recommendations, preferences, output_json)
    generate_markdown_report(report, output_md)
    
    print("=" * 50)
    print("推荐生成完成！")
    print(f"JSON 报告: {output_json}")
    print(f"Markdown 报告: {output_md}")
    print("=" * 50)


if __name__ == '__main__':
    main()
