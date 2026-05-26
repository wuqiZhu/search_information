#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrendRadar Obsidian 同步脚本
将信号自动同步到 Obsidian 知识库
"""

import os
import sys
import json
import glob
import hashlib
from datetime import datetime
from pathlib import Path
from collections import defaultdict


# 分类规则
CATEGORIES = {
    "01-嵌入式Linux": ["嵌入式Linux", "Embedded Linux", "Linux内核", "Linux Kernel"],
    "02-BSP开发": ["BSP", "Board Support Package", "板级支持包"],
    "03-设备驱动": ["设备驱动", "Device Driver", "Device Tree", "DTS"],
    "04-RISC-V": ["RISC-V", "RISC V"],
    "05-IoT": ["IoT", "物联网", "边缘计算", "Edge Computing", "AIoT"]
}


def load_config():
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"加载配置失败: {e}")
        return {}


def classify_signal(signal: dict) -> str:
    """根据关键词对信号分类"""
    keywords = signal.get('keywords', [])
    content = f"{signal.get('title', '')} {signal.get('content', '')}"
    
    # 遍历分类规则
    for category, category_keywords in CATEGORIES.items():
        for keyword in category_keywords:
            if keyword.lower() in content.lower() or keyword in keywords:
                return category
    
    # 如果没有匹配的分类，返回收件箱
    return "00-收件箱"


def generate_obsidian_note(signal: dict, category: str) -> str:
    """生成 Obsidian 格式的 Markdown 笔记"""
    title = signal.get('title', '未命名')
    source = signal.get('source', '未知')
    url = signal.get('url', '')
    timestamp = signal.get('timestamp', '')
    keywords = signal.get('keywords', [])
    relevance_score = signal.get('relevance_score', 0)
    content = signal.get('content', '')
    
    # 生成标签
    tags = [f"#{kw.replace(' ', '_')}" for kw in keywords[:5]]
    tags_str = ' '.join(tags)
    
    # 生成笔记内容
    note = f"""---
title: {title}
source: {source}
url: {url}
created: {timestamp}
relevance: {relevance_score}
tags: {', '.join(keywords[:5])}
---

# {title}

## 基本信息

- **来源**: {source}
- **时间**: {timestamp}
- **相关性**: {relevance_score:.2f}
- **链接**: [{url}]({url})

## 关键词

{tags_str}

## 内容摘要

{content[:500]}{'...' if len(content) > 500 else ''}

## 原文链接

[查看原文]({url})

---

*由 TrendRadar 自动同步*
"""
    return note


def sync_signal_to_obsidian(signal: dict, obsidian_path: str):
    """同步单个信号到 Obsidian"""
    # 分类
    category = classify_signal(signal)
    
    # 生成笔记
    note_content = generate_obsidian_note(signal, category)
    
    # 生成文件名
    title = signal.get('title', '未命名')[:50]
    # 清理文件名中的非法字符
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_title:
        safe_title = hashlib.md5(signal.get('url', '').encode()).hexdigest()[:8]
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{safe_title}.md"
    
    # 确保目录存在
    category_path = os.path.join(obsidian_path, category)
    os.makedirs(category_path, exist_ok=True)
    
    # 保存文件
    filepath = os.path.join(category_path, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(note_content)
    
    return filepath, category


def load_synced_signals(sync_file: str) -> set:
    """加载已同步的信号记录"""
    if os.path.exists(sync_file):
        try:
            with open(sync_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get('synced', []))
        except:
            pass
    return set()


def save_synced_signals(sync_file: str, synced: set):
    """保存已同步的信号记录"""
    os.makedirs(os.path.dirname(sync_file), exist_ok=True)
    with open(sync_file, 'w', encoding='utf-8') as f:
        json.dump({'synced': list(synced)}, f)


def get_signal_hash(signal: dict) -> str:
    """生成信号的唯一哈希"""
    content = f"{signal.get('url', '')}{signal.get('title', '')}"
    return hashlib.md5(content.encode()).hexdigest()


def main():
    """主函数"""
    # 获取项目路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    trendradar_dir = os.path.dirname(script_dir)
    project_dir = os.path.dirname(trendradar_dir)
    
    signals_dir = os.path.join(trendradar_dir, 'data', 'signals')
    obsidian_path = os.path.join(project_dir, 'knowledge_base', 'obsidian')
    sync_file = os.path.join(trendradar_dir, 'data', 'synced_signals.json')
    
    print("=" * 50)
    print("TrendRadar Obsidian 同步")
    print("=" * 50)
    
    # 加载已同步记录
    synced_hashes = load_synced_signals(sync_file)
    print(f"已同步 {len(synced_hashes)} 个信号")
    
    # 扫描信号文件
    if not os.path.exists(signals_dir):
        print(f"信号目录不存在: {signals_dir}")
        return
    
    signal_files = glob.glob(os.path.join(signals_dir, '*.json'))
    print(f"找到 {len(signal_files)} 个信号文件")
    
    # 同步信号
    synced_count = 0
    skipped_count = 0
    
    for filepath in signal_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                signal = json.load(f)
            
            # 检查是否已同步
            signal_hash = get_signal_hash(signal)
            if signal_hash in synced_hashes:
                skipped_count += 1
                continue
            
            # 同步到 Obsidian
            note_path, category = sync_signal_to_obsidian(signal, obsidian_path)
            
            # 记录已同步
            synced_hashes.add(signal_hash)
            synced_count += 1
            
            print(f"[OK] 同步: {signal.get('title', '未命名')[:30]}... -> {category}")
            
        except Exception as e:
            print(f"[FAIL] 同步失败 {filepath}: {e}")
    
    # 保存同步记录
    save_synced_signals(sync_file, synced_hashes)
    
    print("=" * 50)
    print(f"同步完成: 新增 {synced_count} 个，跳过 {skipped_count} 个")
    print(f"知识库路径: {obsidian_path}")
    print("=" * 50)


if __name__ == '__main__':
    main()
