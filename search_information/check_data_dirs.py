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

run('ls -la /root/projects/data/', '数据目录总览')
run('ls -la /root/projects/data/search_information/', 'search_information 数据')
run('ls -la /root/projects/data/knowledge_base/', 'knowledge_base 数据')
run('ls -la /root/projects/data/find_job/', 'find_job 数据')
run('ls -la /root/projects/data/invest/', 'invest 数据')
run('find /root/projects/data/ -name "*.db" -type f', '查找所有数据库文件')

ssh.close()
