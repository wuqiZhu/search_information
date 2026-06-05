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

run('docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"', '容器状态')
run('docker logs --tail 5 analyser 2>&1', 'analyser 日志')
run('docker logs --tail 3 trendradar 2>&1', 'trendradar 日志')

ssh.close()
