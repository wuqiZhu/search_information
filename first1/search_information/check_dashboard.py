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

# 检查 Dashboard 容器内部的目录结构
run('docker exec dashboard ls -la /app/data/', 'Dashboard 容器 /app/data/ 目录')
run('docker exec dashboard ls -la /app/data/search_information/', 'Dashboard 容器 /app/data/search_information/ 目录')
run('docker exec dashboard find /app/data/ -name "*.db" -type f', 'Dashboard 容器中的数据库文件')

# 检查 Dashboard 日志（查找数据库路径）
run('docker logs dashboard 2>&1 | grep -i "数据库路径"', 'Dashboard 数据库路径日志')

ssh.close()
