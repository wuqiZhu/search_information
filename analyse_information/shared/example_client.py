#!/usr/bin/env python3
"""
通知中心客户端使用示例
"""
import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(__file__))

from notification_client import add_signal, update_preference, process_queue, get_stats, health_check

def example_add_signal():
    """示例：添加信号"""
    signal = {
        'title': 'Linux 6.12 正式发布',
        'url': 'https://www.kernel.org/',
        'content': 'Linux 6.12 内核正式发布，包含多项性能优化和新功能...',
        'source': 'Kernel.org',
        'keywords': ['Linux内核', 'kernel', '新版本'],
        'relevance_score': 0.8
    }
    
    success = add_signal(signal, source='trendradar')
    print(f"Add signal: {'Success' if success else 'Failed'}")

def example_update_preference():
    """示例：更新偏好"""
    signal = {
        'title': 'RISC-V 开发板推荐',
        'url': 'https://example.com',
        'content': 'RISC-V 开发板推荐...',
        'source': 'Hackaday',
        'keywords': ['RISC-V', '开发板']
    }
    
    success = update_preference(signal, action='like')
    print(f"Update preference: {'Success' if success else 'Failed'}")

def example_process_queue():
    """示例：处理队列"""
    success = process_queue()
    print(f"Process queue: {'Success' if success else 'Failed'}")

def example_get_stats():
    """示例：获取统计"""
    stats = get_stats()
    if stats:
        print(f"Stats: {stats}")
    else:
        print("Failed to get stats")

def example_health_check():
    """示例：健康检查"""
    is_healthy = health_check()
    print(f"Health check: {'Healthy' if is_healthy else 'Unhealthy'}")

if __name__ == '__main__':
    print("=== Notification Center Client Example ===\n")
    
    print("1. Health Check:")
    example_health_check()
    print()
    
    print("2. Add Signal:")
    example_add_signal()
    print()
    
    print("3. Update Preference:")
    example_update_preference()
    print()
    
    print("4. Process Queue:")
    example_process_queue()
    print()
    
    print("5. Get Stats:")
    example_get_stats()
    print()
    
    print("=== Example completed ===")
