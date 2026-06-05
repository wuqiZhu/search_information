#!/usr/bin/env python3
"""
测试通知中心模块
"""
import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(__file__))

from notification_center import NotificationCenter

def test_notification_center():
    """测试通知中心"""
    print("=== Testing Notification Center ===\n")
    
    # 创建通知中心实例
    center = NotificationCenter()
    
    # 测试添加信号
    print("1. Testing add_signal:")
    signal1 = {
        'title': 'Linux 6.12 正式发布',
        'url': 'https://www.kernel.org/',
        'content': 'Linux 6.12 内核正式发布，包含多项性能优化和新功能...',
        'source': 'Kernel.org',
        'keywords': ['Linux内核', 'kernel', '新版本'],
        'relevance_score': 0.8
    }
    
    success = center.add_signal(signal1, source='trendradar')
    print(f"   Add signal 1: {'Success' if success else 'Failed'}")
    
    signal2 = {
        'title': '大疆嵌入式实习岗位',
        'url': 'https://www.zhipin.com/job_detail/123.html',
        'content': '大疆创新招聘嵌入式开发实习生...',
        'source': 'Boss直聘',
        'keywords': ['实习', '嵌入式开发', 'BSP'],
        'relevance_score': 0.9
    }
    
    success = center.add_signal(signal2, source='find_job')
    print(f"   Add signal 2: {'Success' if success else 'Failed'}")
    
    # 测试获取统计信息
    print("\n2. Testing get_stats:")
    stats = center.get_stats()
    print(f"   Stats: {stats}")
    
    # 测试处理队列
    print("\n3. Testing process_queue:")
    center.process_queue()
    print(f"   Queue processed")
    
    # 测试重复信号（队列已清空，所以不会重复）
    print("\n4. Testing duplicate detection:")
    success = center.add_signal(signal1, source='trendradar')
    print(f"   Add duplicate signal: {'Success' if success else 'Failed'}")
    
    # 再次处理队列
    print("\n5. Testing process_queue again:")
    center.process_queue()
    print(f"   Queue processed")
    
    # 测试更新偏好
    print("\n6. Testing update_preferences:")
    center.update_preferences(signal1, 'like')
    center.update_preferences(signal2, 'dislike')
    print(f"   Updated preferences")
    
    # 再次获取统计信息
    print("\n7. Testing get_stats after preferences:")
    stats = center.get_stats()
    print(f"   Stats: {stats}")
    
    print("\n=== Test completed ===")

if __name__ == '__main__':
    test_notification_center()
