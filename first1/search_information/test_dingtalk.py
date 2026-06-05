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

# 直接测试钉钉 Webhook
import os
DINGTALK_TOKEN = os.environ.get('DINGTALK_TOKEN', 'YOUR_TOKEN_HERE')
run(f'curl -s -X POST "https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_TOKEN}" -H "Content-Type: application/json" -d \'{{"msgtype":"text","text":{{"content":"测试消息"}}}}\'', '直接测试钉钉 Webhook')

ssh.close()
