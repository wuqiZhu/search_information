#!/usr/bin/env python3
"""
测试通知中心集成
"""
import sys
import os

# 添加通知中心客户端路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'analyse_information', 'shared'))

# 测试导入
try:
    from notification_client import add_signal, process_queue
    print('Notification center client imported successfully')
    
    # 测试添加信号
    signal = {
        'title': '测试信号 - Linux 6.12 发布',
        'url': 'https://www.kernel.org/',
        'content': 'Linux 6.12 内核正式发布...',
        'source': 'Kernel.org',
        'keywords': ['Linux内核', 'kernel'],
        'relevance_score': 0.8
    }
    
    success = add_signal(signal, source='trendradar')
    print(f'Add signal: {success}')
    
    # 处理队列
    process_queue()
    print('Queue processed')
    
except ImportError as e:
    print(f'Import error: {e}')
except Exception as e:
    print(f'Error: {e}')
