#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrendRadar 智能摘要增强器
更精准的内容提取，提取关键信息，生成对比分析
"""

import os
import sys
import json
import re
from datetime import datetime
from pathlib import Path


def extract_key_info(content: str) -> dict:
    """提取关键信息"""
    info = {
        'versions': [],
        'dates': [],
        'urls': [],
        'emails': [],
        'numbers': [],
        'technical_terms': []
    }
    
    # 提取版本号
    version_patterns = [
        r'v?\d+\.\d+\.\d+',  # v1.2.3 或 1.2.3
        r'\d+\.\d+',  # 1.2
        r'版本\s*[:：]\s*\d+[\.\d]*',  # 版本: 1.2.3
    ]
    for pattern in version_patterns:
        versions = re.findall(pattern, content)
        info['versions'].extend(versions)
    
    # 提取日期
    date_patterns = [
        r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',  # 2024-01-01
        r'\d{1,2}[-/]\d{1,2}[-/]\d{4}',  # 01-01-2024
        r'\d{4}年\d{1,2}月\d{1,2}日',  # 2024年1月1日
    ]
    for pattern in date_patterns:
        dates = re.findall(pattern, content)
        info['dates'].extend(dates)
    
    # 提取 URL
    url_pattern = r'https?://[^\s<>\"\')\]]+'
    urls = re.findall(url_pattern, content)
    info['urls'] = list(set(urls))[:10]  # 最多10个
    
    # 提取邮箱
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, content)
    info['emails'] = list(set(emails))[:5]
    
    # 提取数字（可能是重要指标）
    number_pattern = r'\b\d+\.?\d*\s*(?:%|ms|秒|分钟|小时|MB|GB|KB|个|条|次)\b'
    numbers = re.findall(number_pattern, content)
    info['numbers'] = numbers[:10]
    
    # 提取技术术语
    technical_terms = [
        'Linux', 'Kernel', 'Driver', 'BSP', 'RISC-V', 'ARM', 'MIPS',
        'GPIO', 'I2C', 'SPI', 'UART', 'PCIe', 'USB', 'DMA',
        'U-Boot', 'Buildroot', 'Yocto', 'OpenWrt',
        'Device Tree', 'DTS', 'DTB',
        'RTOS', 'FreeRTOS', 'Zephyr',
        'Docker', 'Kubernetes', 'CI/CD'
    ]
    for term in technical_terms:
        if term.lower() in content.lower():
            info['technical_terms'].append(term)
    
    return info


def generate_smart_summary(content: str, max_length: int = 500) -> str:
    """生成智能摘要"""
    if not content:
        return ""
    
    # 提取关键信息
    key_info = extract_key_info(content)
    
    # 生成摘要
    summary_parts = []
    
    # 原始内容摘要
    if len(content) > max_length:
        # 尝试按句子分割
        sentences = re.split(r'[。！？.!?]', content)
        summary = ''
        for sentence in sentences:
            if len(summary) + len(sentence) < max_length:
                summary += sentence + '。'
            else:
                break
        summary_parts.append(summary)
    else:
        summary_parts.append(content)
    
    # 添加关键信息
    if key_info['versions']:
        summary_parts.append(f"\n📌 版本: {', '.join(set(key_info['versions'][:3]))}")
    
    if key_info['dates']:
        summary_parts.append(f"📅 日期: {', '.join(set(key_info['dates'][:3]))}")
    
    if key_info['technical_terms']:
        summary_parts.append(f"🔧 技术: {', '.join(set(key_info['technical_terms'][:5]))}")
    
    if key_info['numbers']:
        summary_parts.append(f"📊 指标: {', '.join(key_info['numbers'][:3])}")
    
    return '\n'.join(summary_parts)


def analyze_content_quality(content: str) -> dict:
    """分析内容质量"""
    quality = {
        'length': len(content),
        'has_code': bool(re.search(r'```|`.*`|def |class |import |function', content)),
        'has_links': bool(re.search(r'https?://', content)),
        'has_images': bool(re.search(r'!\[.*\]\(.*\)|<img', content)),
        'has_tables': bool(re.search(r'\|.*\|', content)),
        'has_headings': bool(re.search(r'^#{1,6}\s', content, re.MULTILINE)),
        'technical_depth': 0,
        'readability': 0
    }
    
    # 计算技术深度
    technical_indicators = [
        r'代码', r'实现', r'源码', r'架构', r'设计模式',
        r'算法', r'数据结构', r'性能优化', r'内存管理',
        r'并发', r'多线程', r'异步', r'同步',
        r'API', r'接口', r'协议', r'标准'
    ]
    for indicator in technical_indicators:
        if re.search(indicator, content, re.IGNORECASE):
            quality['technical_depth'] += 1
    
    # 计算可读性
    if quality['length'] > 0:
        # 简单的可读性指标
        avg_sentence_length = quality['length'] / max(1, content.count('。') + content.count('.') + 1)
        if avg_sentence_length < 50:
            quality['readability'] += 1
        if quality['has_headings']:
            quality['readability'] += 1
        if quality['has_tables']:
            quality['readability'] += 1
    
    return quality


def generate_content_report(signal: dict) -> dict:
    """生成内容报告"""
    content = signal.get('content', '')
    
    report = {
        'title': signal.get('title', ''),
        'source': signal.get('source', ''),
        'url': signal.get('url', ''),
        'timestamp': signal.get('timestamp', ''),
        'keywords': signal.get('keywords', []),
        'relevance_score': signal.get('relevance_score', 0),
        'key_info': extract_key_info(content),
        'quality': analyze_content_quality(content),
        'smart_summary': generate_smart_summary(content)
    }
    
    return report


def process_signals(signals_dir: str, output_dir: str):
    """处理信号文件"""
    import glob
    
    os.makedirs(output_dir, exist_ok=True)
    
    processed = 0
    for filepath in glob.glob(os.path.join(signals_dir, '*.json')):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                signal = json.load(f)
            
            # 生成内容报告
            report = generate_content_report(signal)
            
            # 保存报告
            filename = os.path.basename(filepath)
            output_file = os.path.join(output_dir, f"enhanced_{filename}")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            processed += 1
            
        except Exception as e:
            print(f"处理失败 {filepath}: {e}")
    
    return processed


def main():
    """主函数"""
    # 获取项目路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    trendradar_dir = os.path.dirname(script_dir)
    
    signals_dir = os.path.join(trendradar_dir, 'data', 'signals')
    output_dir = os.path.join(trendradar_dir, 'data', 'enhanced_signals')
    
    print("=" * 50)
    print("TrendRadar 智能摘要增强器")
    print("=" * 50)
    
    # 处理信号
    processed = process_signals(signals_dir, output_dir)
    
    print("=" * 50)
    print(f"处理完成: {processed} 个信号")
    print(f"输出目录: {output_dir}")
    print("=" * 50)


if __name__ == '__main__':
    main()
