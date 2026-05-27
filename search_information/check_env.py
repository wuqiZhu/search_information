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

# 检查 Dashboard 容器环境变量
run('docker exec dashboard env | grep -i data', 'Dashboard 环境变量')

# 检查服务器上的 docker-compose.yml
run('grep -A 10 "dashboard:" /root/projects/docker-compose.yml', 'docker-compose.yml 中的 dashboard 配置')

# 检查服务器上的 docker-compose-server.yml
run('grep -A 10 "dashboard:" /root/projects/search_information/search_information/docker-compose-server.yml', 'docker-compose-server.yml 中的 dashboard 配置')

ssh.close()
