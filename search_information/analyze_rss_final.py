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

# TrendRadar 各平台新闻数量（用 dashboard 容器）
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/news/2026-05-27.db\'); cursor=conn.execute(\'SELECT platform_id, COUNT(*) as count FROM news_items GROUP BY platform_id ORDER BY count DESC\'); print(\'TrendRadar 各平台新闻:\'); [print(f\'  {r[0]}: {r[1]} 条\') for r in cursor.fetchall()]; conn.close()"', 'TrendRadar 平台统计')

# RSS 各源文章数量（用 dashboard 容器）
run('docker exec dashboard python3 -c "import sqlite3; conn=sqlite3.connect(\'/app/data/search_information/rss/2026-05-27.db\'); cursor=conn.execute(\'SELECT feed_id, COUNT(*) as count FROM rss_items GROUP BY feed_id ORDER BY count DESC\'); print(\'RSS 各源文章:\'); [print(f\'  {r[0]}: {r[1]} 篇\') for r in cursor.fetchall()]; conn.close()"', 'RSS 源统计')

ssh.close()
