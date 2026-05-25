-- 统一数据库初始化脚本
-- 在 SQLite 中执行此脚本

-- 1. 信号表：存储采集到的原始信号
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
);

-- 2. 分析结果表：存储AI分析结果
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
);

-- 3. 通知记录表：存储发送的通知
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
);

-- 4. 用户反馈表：存储用户对信号的反馈
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    action TEXT NOT NULL,
    feedback_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

-- 5. 任务状态表：存储系统任务状态
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. 知识库笔记表：存储Obsidian笔记信息
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
);

-- 7. 每日简报表：存储每日简报信息
CREATE TABLE IF NOT EXISTS daily_digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    file_path TEXT,
    signal_count INTEGER,
    high_score_count INTEGER,
    medium_score_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);
CREATE INDEX IF NOT EXISTS idx_signals_processed ON signals(processed);
CREATE INDEX IF NOT EXISTS idx_signals_priority ON signals(priority);
CREATE INDEX IF NOT EXISTS idx_signals_collected_at ON signals(collected_at);
CREATE INDEX IF NOT EXISTS idx_analysis_signal_id ON analysis(signal_id);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
