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

# 检查 TrendRadar 数据库表结构
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/news/2026-05-27.db\'); cursor=conn.execute(\'SELECT name FROM sqlite_master WHERE type=\\\'table\\\'\'); print(\'表:\', [r[0] for r in cursor.fetchall()]); conn.close()"', 'TrendRadar 数据库表')

# 检查 TrendRadar 数据库数据量
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/news/2026-05-27.db\'); cursor=conn.execute(\'SELECT COUNT(*) FROM news\'); print(\'新闻数量:\', cursor.fetchone()[0]); conn.close()"', 'TrendRadar 数据量')

# 检查 RSS 数据库表结构
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/rss/2026-05-27.db\'); cursor=conn.execute(\'SELECT name FROM sqlite_master WHERE type=\\\'table\\\'\'); print(\'表:\', [r[0] for r in cursor.fetchall()]); conn.close()"', 'RSS 数据库表')

# 检查 RSS 数据库数据量
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/rss/2026-05-27.db\'); cursor=conn.execute(\'SELECT COUNT(*) FROM articles\'); print(\'文章数量:\', cursor.fetchone()[0]); conn.close()"', 'RSS 数据量')

ssh.close()
