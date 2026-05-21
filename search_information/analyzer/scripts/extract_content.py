#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容提取脚本
使用 Defuddle 提取网页干净正文
"""

import os
import sys
import json
import subprocess
import yaml
from datetime import datetime
from pathlib import Path


def load_config():
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def extract_with_defuddle(url: str, output_format: str = 'markdown') -> dict:
    """使用 Defuddle 提取网页内容"""
    try:
        # 调用 defuddle 命令
        cmd = ['defuddle', 'parse', url, '--markdown']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return {
                'success': True,
                'content': result.stdout,
                'url': url,
                'timestamp': datetime.now().isoformat()
            }
        else:
            return {
                'success': False,
                'error': result.stderr,
                'url': url,
                'timestamp': datetime.now().isoformat()
            }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': '提取超时',
            'url': url,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url,
            'timestamp': datetime.now().isoformat()
        }


def save_raw_content(content: dict, output_dir: str = '../knowledge_base/raw'):
    """保存原始内容"""
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    
    return filepath


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python extract_content.py <URL>")
        sys.exit(1)
    
    url = sys.argv[1]
    config = load_config()
    
    print(f"正在提取: {url}")
    
    # 提取内容
    result = extract_with_defuddle(url, config['defuddle']['output_format'])
    
    if result['success']:
        print("提取成功！")
        print(f"内容长度: {len(result['content'])} 字符")
        
        # 保存原始内容
        filepath = save_raw_content(result)
        print(f"已保存到: {filepath}")
        
        # 输出内容预览
        print("\n内容预览:")
        print("-" * 50)
        print(result['content'][:500] + "..." if len(result['content']) > 500 else result['content'])
        print("-" * 50)
    else:
        print(f"提取失败: {result['error']}")
        sys.exit(1)


if __name__ == '__main__':
    main()
