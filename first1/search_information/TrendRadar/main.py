#!/usr/bin/env python3
"""TrendRadar 入口 - 使用新版 trendradar 包"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from trendradar.__main__ import main
    main()
except ImportError:
    print("错误: 未找到 trendradar 包，请确认 trendradar/ 目录存在")
    print("旧版入口已移至 legacy/main_old.py")
    sys.exit(1)
