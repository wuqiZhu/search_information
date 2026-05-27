import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('188.166.249.182', username='root', password='13979831637Zhu@', timeout=10)

def run(cmd, label=""):
    if label:
        print(f'\n{"="*60}')
        print(f'>>> {label}')
        print(f'{"="*60}')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out:
        print(out.strip())
    if err:
        print(f'[STDERR] {err.strip()}')
    return out, err

# 统计各 RSS 源的文章数量
run('''docker exec analyser python3 -c "
import sqlite3
import os
from pathlib import Path

db_path = '/app/data/search_information/rss/2026-05-27.db'
if not os.path.exists(db_path):
    print('数据库不存在')
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.execute('''
        SELECT feed_id, COUNT(*) as count 
        FROM rss_items 
        GROUP BY feed_id 
        ORDER BY count DESC
    ''')
    print('RSS源文章数量统计:')
    print('-' * 40)
    for row in cursor.fetchall():
        print(f'{row[0]}: {row[1]} 篇')
    conn.close()
"''', 'RSS 源文章数量统计')

# 统计 TrendRadar 各平台的新闻数量
run('''docker exec analyser python3 -c "
import sqlite3
import os

db_path = '/app/data/search_information/news/2026-05-27.db'
if not os.path.exists(db_path):
    print('数据库不存在')
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.execute('''
        SELECT platform_id, COUNT(*) as count 
        FROM news_items 
        GROUP BY platform_id 
        ORDER BY count DESC
    ''')
    print('TrendRadar 各平台新闻数量:')
    print('-' * 40)
    for row in cursor.fetchall():
        print(f'{row[0]}: {row[1]} 条')
    conn.close()
"''', 'TrendRadar 各平台新闻数量')

ssh.close()
