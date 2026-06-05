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

# 检查知识库目录
run('ls -la /root/projects/data/knowledge_base/', '知识库目录')
run('ls -la /root/projects/data/knowledge_base/obsidian/', 'Obsidian 目录')
run('find /root/projects/data/knowledge_base/obsidian/ -name "*.md" -type f | head -10', 'Markdown 文件示例')
run('find /root/projects/data/knowledge_base/obsidian/ -name "*.md" -type f | wc -l', 'Markdown 文件数量')

ssh.close()
