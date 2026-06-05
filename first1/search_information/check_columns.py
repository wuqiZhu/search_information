from ssh_helper import get_ssh_client

ssh = get_ssh_client()

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

# 检查 news_items 表结构
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/news/2026-05-27.db\'); cursor=conn.execute(\'PRAGMA table_info(news_items)\'); print(\'news_items 列:\', [r[1] for r in cursor.fetchall()]); conn.close()"', 'news_items 表结构')

# 检查 news_items 数据量
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/news/2026-05-27.db\'); cursor=conn.execute(\'SELECT COUNT(*) FROM news_items\'); print(\'新闻数量:\', cursor.fetchone()[0]); conn.close()"', 'news_items 数据量')

# 检查 news_items 样例数据
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/news/2026-05-27.db\'); cursor=conn.execute(\'SELECT * FROM news_items LIMIT 2\'); print(\'样例数据:\'); [print(r) for r in cursor.fetchall()]; conn.close()"', 'news_items 样例数据')

# 检查 rss_items 表结构
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/rss/2026-05-27.db\'); cursor=conn.execute(\'PRAGMA table_info(rss_items)\'); print(\'rss_items 列:\', [r[1] for r in cursor.fetchall()]); conn.close()"', 'rss_items 表结构')

# 检查 rss_items 数据量
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/rss/2026-05-27.db\'); cursor=conn.execute(\'SELECT COUNT(*) FROM rss_items\'); print(\'文章数量:\', cursor.fetchone()[0]); conn.close()"', 'rss_items 数据量')

ssh.close()
