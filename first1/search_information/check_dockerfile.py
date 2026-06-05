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

# 检查 docker-compose.yml 中 dashboard 的配置
run('grep -A 15 "dashboard:" /root/projects/docker-compose.yml', 'docker-compose.yml 中的 dashboard 配置')

# 检查服务器上 dashboard_service 目录的文件
run('ls -la /root/projects/search_information/search_information/dashboard_service/', '服务器上的 dashboard_service 目录')

# 检查服务器上 server.py 是否包含 news_items
run('grep -c "news_items" /root/projects/search_information/search_information/dashboard_service/server.py', '服务器上 news_items 出现次数')

# 检查 Dockerfile
run('cat /root/projects/search_information/search_information/dashboard_service/Dockerfile', 'Dashboard Dockerfile')

ssh.close()
