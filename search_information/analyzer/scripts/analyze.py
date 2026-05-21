#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信息分析主脚本
整合内容提取、AI 分析、知识沉淀
"""

import os
import sys
import json
import yaml
import subprocess
from datetime import datetime
from pathlib import Path


def load_config():
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def extract_content(url: str) -> dict:
    """提取网页内容"""
    script_path = os.path.join(os.path.dirname(__file__), 'extract_content.py')
    result = subprocess.run(
        ['python', script_path, url],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    if result.returncode == 0:
        # 读取提取的内容
        raw_dir = os.path.join(os.path.dirname(__file__), '..', 'knowledge_base', 'raw')
        files = sorted(Path(raw_dir).glob('*.json'), key=os.path.getmtime, reverse=True)
        if files:
            with open(files[0], 'r', encoding='utf-8') as f:
                return json.load(f)
    
    return None


def analyze_content(raw_file: str) -> dict:
    """分析内容"""
    script_path = os.path.join(os.path.dirname(__file__), 'ai_analyze.py')
    result = subprocess.run(
        ['python', script_path, raw_file],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result.returncode == 0:
        # 读取分析结果
        analyzed_dir = os.path.join(os.path.dirname(__file__), '..', 'knowledge_base', 'analyzed')
        files = sorted(Path(analyzed_dir).glob('*.json'), key=os.path.getmtime, reverse=True)
        if files:
            with open(files[0], 'r', encoding='utf-8') as f:
                return json.load(f)
    
    return None


def process_signal(signal: dict):
    """处理单个信号"""
    url = signal.get('url', '')
    if not url:
        print("信号无 URL，跳过")
        return
    
    print(f"\n处理信号: {signal.get('title', '未知')}")
    print(f"URL: {url}")
    
    # 提取内容
    print("正在提取内容...")
    raw_content = extract_content(url)
    
    if not raw_content:
        print("内容提取失败")
        return
    
    # 保存原始内容
    raw_dir = os.path.join(os.path.dirname(__file__), '..', 'knowledge_base', 'raw')
    os.makedirs(raw_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    raw_file = os.path.join(raw_dir, f"{timestamp}.json")
    
    with open(raw_file, 'w', encoding='utf-8') as f:
        json.dump(raw_content, f, ensure_ascii=False, indent=2)
    
    print(f"原始内容已保存: {raw_file}")
    
    # 分析内容
    print("正在分析内容...")
    analyzed_content = analyze_content(raw_file)
    
    if analyzed_content:
        print(f"分析完成！分类: {analyzed_content.get('category', '未知')}")
        print(f"相关性评分: {analyzed_content.get('relevance_score', 0):.2f}")
    else:
        print("内容分析失败")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python analyze.py <URL>              # 分析单个 URL")
        print("  python analyze.py --signals <JSON>   # 处理信号文件")
        sys.exit(1)
    
    if sys.argv[1] == '--signals':
        # 处理信号文件
        if len(sys.argv) < 3:
            print("请指定信号文件路径")
            sys.exit(1)
        
        signals_file = sys.argv[2]
        with open(signals_file, 'r', encoding='utf-8') as f:
            signals = json.load(f)
        
        print(f"处理 {len(signals)} 个信号...")
        for signal in signals:
            process_signal(signal)
    else:
        # 处理单个 URL
        url = sys.argv[1]
        signal = {
            'title': '手动分析',
            'url': url,
            'source': '手动输入'
        }
        process_signal(signal)


if __name__ == '__main__':
    main()
