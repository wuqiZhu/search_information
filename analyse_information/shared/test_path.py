#!/usr/bin/env python3
"""
测试路径计算
"""
import os

# 计算 TrendRadar 配置路径
script_dir = os.path.dirname(os.path.abspath(__file__))
trendradar_config_path = os.path.join(
    script_dir, '..', '..', '..', 
    'search_information', 'TrendRadar', 'config.yaml'
)

print(f"Script dir: {script_dir}")
print(f"TrendRadar config path: {trendradar_config_path}")
print(f"Absolute path: {os.path.abspath(trendradar_config_path)}")
print(f"File exists: {os.path.exists(trendradar_config_path)}")
