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

# 检查 docker-compose.yml 中 notification-center 的配置
run('grep -A 15 "notification-center:" /root/projects/docker-compose.yml', 'notification-center 配置')

# 检查 .env 文件内容
run('cat /root/projects/.env', '.env 文件内容')

# 检查 .env 文件是否存在
run('ls -la /root/projects/.env', '.env 文件信息')

# 检查通知中心容器的所有环境变量
run('docker exec notification-center env', '通知中心容器所有环境变量')

ssh.close()
