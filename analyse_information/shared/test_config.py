#!/usr/bin/env python3
"""
测试通知中心配置读取
"""
import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(__file__))

from notification_center import NotificationCenter

def test_config():
    """测试配置读取"""
    print("=== Testing Notification Center Config ===\n")
    
    # 创建通知中心实例
    center = NotificationCenter()
    
    # 检查配置
    print("1. DingTalk Config:")
    print(f"   Webhook: {center.dingtalk_webhook[:30]}..." if center.dingtalk_webhook else "   Webhook: Not configured")
    print(f"   Secret: {'*' * 10}" if center.dingtalk_secret else "   Secret: Not configured")
    
    # 检查完整配置
    print("\n2. Full Config:")
    dingtalk_config = center.config.get('dingtalk', {})
    print(f"   Enabled: {dingtalk_config.get('enabled', False)}")
    print(f"   Feedback URL: {dingtalk_config.get('feedback_url', 'Not configured')}")
    
    print("\n=== Test completed ===")

if __name__ == '__main__':
    test_config()
