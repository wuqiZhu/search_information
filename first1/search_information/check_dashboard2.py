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

# 检查 Dashboard 所有日志
run('docker logs dashboard 2>&1 | tail -30', 'Dashboard 最近日志')

# 测试 Dashboard API 返回的完整数据
run('curl -s http://localhost:5060/api/today | python3 -m json.tool', 'Dashboard API 完整数据')

# 检查 Dashboard 容器环境变量
run('docker exec dashboard env | grep -i data', 'Dashboard 环境变量')

ssh.close()
