#!/usr/bin/env python3
"""
统一数据库初始化脚本
创建系统所需的所有数据表
"""
import sqlite3
import os
from datetime import datetime

# 获取当前脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(SCRIPT_DIR, 'data')
DB_PATH = os.path.join(DB_DIR, 'system.db')

def init_database():
    """初始化数据库，创建所有必要的表"""
    # 确保数据目录存在
    os.makedirs(DB_DIR, exist_ok=True)
    
    print(f"Database directory: {DB_DIR}")
    print(f"Database path: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 信号表：存储采集到的原始信号
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            content TEXT,
            summary TEXT,
            keywords TEXT,
            relevance_score REAL DEFAULT 0,
            priority TEXT DEFAULT 'P2',
            category TEXT,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed BOOLEAN DEFAULT 0,
            hash TEXT UNIQUE,
            metadata TEXT
        )
    ''')
    
    # 2. 分析结果表：存储AI分析结果
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            score REAL,
            reason TEXT,
            translation TEXT,
            category TEXT,
            difficulty TEXT,
            action TEXT,
            token_usage TEXT,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        )
    ''')
    
    # 3. 通知记录表：存储发送的通知
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            channel TEXT NOT NULL,
            title TEXT,
            content TEXT,
            status TEXT DEFAULT 'pending',
            sent_at TIMESTAMP,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        )
    ''')
    
    # 4. 用户反馈表：存储用户对信号的反馈
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            action TEXT NOT NULL,
            feedback_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        )
    ''')
    
    # 5. 任务状态表：存储系统任务状态
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 6. 知识库笔记表：存储Obsidian笔记信息
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            file_path TEXT,
            title TEXT,
            category TEXT,
            score REAL,
            difficulty TEXT,
            action TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        )
    ''')
    
    # 7. 每日简报表：存储每日简报信息
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            file_path TEXT,
            signal_count INTEGER,
            high_score_count INTEGER,
            medium_score_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_processed ON signals(processed)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_priority ON signals(priority)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_collected_at ON signals(collected_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_analysis_signal_id ON analysis(signal_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status)')
    
    conn.commit()
    conn.close()
    
    print(f"Database initialized successfully: {DB_PATH}")
    return DB_PATH

if __name__ == '__main__':
    init_database()
