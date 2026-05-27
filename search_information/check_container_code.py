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

# 检查容器内 server.py 文件位置
run('docker exec dashboard find /app -name "server.py" -type f', 'server.py 文件位置')

# 检查容器内代码是否包含 news_items
run('docker exec dashboard grep -c "news_items" /app/server.py', 'news_items 出现次数')

# 检查容器内代码是否包含旧表名
run('docker exec dashboard grep -c "FROM news " /app/server.py', '旧表名 FROM news 出现次数')

# 检查容器内代码的数据库查询部分
run('docker exec dashboard grep -A2 "SELECT COUNT" /app/server.py', '数据库查询代码')

ssh.close()
