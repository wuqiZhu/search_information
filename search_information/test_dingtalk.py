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

# 直接测试钉钉 Webhook
run('curl -s -X POST "https://oapi.dingtalk.com/robot/send?access_token=bb83f67a019468a893739be3eec9fbf107e3a33aa4c305747b51ca20a5cab737" -H "Content-Type: application/json" -d \'{"msgtype":"text","text":{"content":"测试消息"}}\'', '直接测试钉钉 Webhook')

ssh.close()
