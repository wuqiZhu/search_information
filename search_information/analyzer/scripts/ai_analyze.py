#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 分析脚本
使用 DeepSeek API 进行内容分析和大白话翻译
"""

import os
import sys
import json
import re
import yaml
import requests
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv


# 加载环境变量（根目录 .env）
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))


# 成本跟踪文件
COST_TRACKER_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'ai_cost_tracker.json')


def resolve_env_vars(obj):
    """递归解析配置中的 ${VAR} 环境变量引用"""
    if isinstance(obj, str):
        pattern = r'\$\{(\w+)\}'
        def replacer(match):
            return os.environ.get(match.group(1), '')
        return re.sub(pattern, replacer, obj)
    elif isinstance(obj, dict):
        return {k: resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [resolve_env_vars(item) for item in obj]
    return obj


def load_config():
    """加载配置文件并解析环境变量"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return resolve_env_vars(config)


def load_cost_tracker() -> dict:
    """加载成本跟踪数据"""
    os.makedirs(os.path.dirname(COST_TRACKER_FILE), exist_ok=True)
    
    if os.path.exists(COST_TRACKER_FILE):
        try:
            with open(COST_TRACKER_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    
    return {
        'today': date.today().isoformat(),
        'daily_calls': 0,
        'daily_cost': 0.0,
        'monthly_calls': 0,
        'monthly_cost': 0.0,
        'total_calls': 0,
        'total_cost': 0.0
    }


def save_cost_tracker(tracker: dict):
    """保存成本跟踪数据"""
    os.makedirs(os.path.dirname(COST_TRACKER_FILE), exist_ok=True)
    with open(COST_TRACKER_FILE, 'w', encoding='utf-8') as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)


def check_cost_limit(tracker: dict, config: dict) -> tuple:
    """检查是否超出成本限制"""
    # 检查是否需要重置每日计数
    today = date.today().isoformat()
    if tracker.get('today') != today:
        tracker['today'] = today
        tracker['daily_calls'] = 0
        tracker['daily_cost'] = 0.0
    
    # 获取限制配置
    cost_limit = config.get('cost_limit', {})
    daily_limit = cost_limit.get('daily_calls', 20)
    daily_cost_limit = cost_limit.get('daily_cost', 2.0)  # 美元
    monthly_limit = cost_limit.get('monthly_calls', 200)
    monthly_cost_limit = cost_limit.get('monthly_cost', 20.0)  # 美元
    
    # 检查每日限制
    if tracker['daily_calls'] >= daily_limit:
        return False, f"已达到每日调用上限 ({daily_limit} 次)"
    if tracker['daily_cost'] >= daily_cost_limit:
        return False, f"已达到每日费用上限 (${daily_cost_limit})"
    
    # 检查每月限制
    if tracker['monthly_calls'] >= monthly_limit:
        return False, f"已达到每月调用上限 ({monthly_limit} 次)"
    if tracker['monthly_cost'] >= monthly_cost_limit:
        return False, f"已达到每月费用上限 (${monthly_cost_limit})"
    
    return True, "OK"


def update_cost_tracker(tracker: dict, tokens_used: int, cost_per_1k_tokens: float = 0.002):
    """更新成本跟踪"""
    cost = (tokens_used / 1000) * cost_per_1k_tokens
    
    tracker['daily_calls'] += 1
    tracker['daily_cost'] += cost
    tracker['monthly_calls'] += 1
    tracker['monthly_cost'] += cost
    tracker['total_calls'] += 1
    tracker['total_cost'] += cost
    
    save_cost_tracker(tracker)


def check_relevance(content: str, keywords: list, min_score: float) -> tuple:
    """检查内容是否与用户相关"""
    score = 0
    matched_keywords = []
    
    for keyword in keywords:
        if keyword.lower() in content.lower():
            score += 1
            matched_keywords.append(keyword)
    
    relevance_score = score / len(keywords) if keywords else 0
    is_relevant = relevance_score >= min_score
    
    return is_relevant, relevance_score, matched_keywords


def classify_content(content: str, categories: list) -> str:
    """对内容进行分类"""
    for category in categories:
        for keyword in category['keywords']:
            if keyword.lower() in content.lower():
                return category['name']
    return '其他'


def translate_to_plain_language(content: str, api_key: str, api_base: str, tracker: dict = None, config: dict = None) -> tuple:
    """将技术内容翻译成大白话，带成本控制"""
    # 检查成本限制
    if tracker and config:
        can_proceed, reason = check_cost_limit(tracker, config)
        if not can_proceed:
            return None, reason
    
    prompt = """请将以下技术内容翻译成大白话，要求：
1. 用简单的语言解释技术概念
2. 说明这个技术对我有什么用
3. 如果有学习资源，列出可以获取的渠道
4. 如果有相关项目或工具，列出名称和链接

技术内容：
{content}

请用中文回答，格式清晰易读。""".format(content=content[:3000])  # 限制内容长度

    try:
        response = requests.post(
            f"{api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": os.environ.get('DEEPSEEK_MODEL', 'mimo-v2-flash'),
                "messages": [
                    {"role": "system", "content": "你是一个技术翻译专家，擅长将复杂的技术内容翻译成普通人能理解的语言。"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 2000,
                "temperature": 0.7
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            translation = result['choices'][0]['message']['content']
            
            # 更新成本跟踪
            if tracker:
                tokens_used = result.get('usage', {}).get('total_tokens', 1000)
                update_cost_tracker(tracker, tokens_used)
            
            return translation, "OK"
        else:
            return None, f"翻译失败: HTTP {response.status_code}"
            
    except Exception as e:
        return None, f"翻译失败: {str(e)}"


def save_analyzed_content(content: dict, output_dir: str = '../knowledge_base/analyzed'):
    """保存分析后的内容"""
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    
    return filepath


def save_to_obsidian(content: dict, category: str, obsidian_path: str):
    """保存到 Obsidian 知识库"""
    # 确定分类目录
    category_path = os.path.join(obsidian_path, category)
    os.makedirs(category_path, exist_ok=True)
    
    # 生成文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    title = content.get('title', '未命名')[:50]
    filename = f"{timestamp}_{title}.md"
    filepath = os.path.join(category_path, filename)
    
    # 生成 Markdown 内容
    md_content = f"""---
title: {content.get('title', '未命名')}
source: {content.get('source', '未知')}
url: {content.get('url', '')}
date: {content.get('timestamp', datetime.now().isoformat())}
category: {category}
relevance_score: {content.get('relevance_score', 0)}
keywords: {', '.join(content.get('keywords', []))}
---

# {content.get('title', '未命名')}

## 来源
- **来源**: {content.get('source', '未知')}
- **链接**: [{content.get('url', '原文')}]({content.get('url', '')})
- **时间**: {content.get('timestamp', datetime.now().isoformat())}

## 关键词
{', '.join(content.get('keywords', []))}

## 原文摘要
{content.get('summary', '无')}

## 大白话翻译
{content.get('translation', '无')}

---
*由 TrendRadar 自动生成*
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    return filepath


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python ai_analyze.py <JSON文件路径>")
        sys.exit(1)
    
    json_file = sys.argv[1]
    config = load_config()
    
    # 加载成本跟踪器
    tracker = load_cost_tracker()
    
    # 检查成本限制
    can_proceed, reason = check_cost_limit(tracker, config)
    if not can_proceed:
        print(f"❌ 成本限制: {reason}")
        print(f"今日调用: {tracker['daily_calls']} 次, 费用: ${tracker['daily_cost']:.4f}")
        print(f"本月调用: {tracker['monthly_calls']} 次, 费用: ${tracker['monthly_cost']:.4f}")
        sys.exit(1)
    
    # 读取原始内容
    with open(json_file, 'r', encoding='utf-8') as f:
        raw_content = json.load(f)
    
    print(f"正在分析: {raw_content.get('url', '未知')}")
    
    # 检查相关性
    is_relevant, relevance_score, matched_keywords = check_relevance(
        raw_content.get('content', ''),
        config['relevance']['keywords'],
        config['relevance']['min_score']
    )
    
    print(f"相关性评分: {relevance_score:.2f}")
    print(f"匹配关键词: {', '.join(matched_keywords)}")
    
    if not is_relevant:
        print("内容与用户不相关，跳过分析")
        sys.exit(0)
    
    # 分类内容
    category = classify_content(raw_content.get('content', ''), config['categories'])
    print(f"内容分类: {category}")
    
    # AI 翻译
    print("正在进行 AI 翻译...")
    api_key = os.environ.get('OPENAI_API_KEY', config['ai']['api_key'])
    api_base = config['ai']['api_base']
    
    translation, status = translate_to_plain_language(
        raw_content.get('content', ''),
        api_key,
        api_base,
        tracker,
        config
    )
    
    if translation is None:
        print(f"❌ AI 翻译失败: {status}")
        sys.exit(1)
    
    # 构建分析结果
    analyzed_content = {
        'title': raw_content.get('title', '未命名'),
        'source': raw_content.get('source', '未知'),
        'url': raw_content.get('url', ''),
        'timestamp': datetime.now().isoformat(),
        'content': raw_content.get('content', ''),
        'summary': raw_content.get('summary', ''),
        'keywords': matched_keywords,
        'relevance_score': relevance_score,
        'category': category,
        'translation': translation
    }
    
    # 保存分析结果
    filepath = save_analyzed_content(analyzed_content)
    print(f"分析结果已保存到: {filepath}")
    
    # 保存到 Obsidian
    obsidian_path = os.path.join(os.path.dirname(__file__), '..', config['knowledge_base']['obsidian_path'])
    obsidian_file = save_to_obsidian(analyzed_content, category, obsidian_path)
    print(f"已保存到 Obsidian: {obsidian_file}")
    
    # 输出成本统计
    print(f"\n📊 成本统计:")
    print(f"  今日调用: {tracker['daily_calls']} 次, 费用: ${tracker['daily_cost']:.4f}")
    print(f"  本月调用: {tracker['monthly_calls']} 次, 费用: ${tracker['monthly_cost']:.4f}")
    print(f"  总计调用: {tracker['total_calls']} 次, 费用: ${tracker['total_cost']:.4f}")
    
    print("\n分析完成！")


if __name__ == '__main__':
    main()
