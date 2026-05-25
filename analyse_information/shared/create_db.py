#!/usr/bin/env python3
import sqlite3
import os

# 获取当前脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(SCRIPT_DIR, 'data')
DB_PATH = os.path.join(DB_DIR, 'system.db')

print(f"Script directory: {SCRIPT_DIR}")
print(f"Database directory: {DB_DIR}")
print(f"Database path: {DB_PATH}")

# 确保目录存在
os.makedirs(DB_DIR, exist_ok=True)

# 检查目录权限
print(f"Directory exists: {os.path.exists(DB_DIR)}")
print(f"Directory writable: {os.access(DB_DIR, os.W_OK)}")

try:
    # 尝试创建数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 创建一个简单的测试表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS test (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    ''')
    
    # 插入测试数据
    cursor.execute("INSERT INTO test (name) VALUES ('test')")
    
    conn.commit()
    conn.close()
    
    print("Database created successfully!")
    print(f"File size: {os.path.getsize(DB_PATH)} bytes")
    
except Exception as e:
    print(f"Error: {e}")
