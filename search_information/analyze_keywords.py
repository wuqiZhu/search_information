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

# 分析关键词命中率（检查 news_items 中的关键词匹配情况）
run('''docker exec dashboard python3 -c "
import sqlite3
from collections import Counter

conn = sqlite3.connect('/app/data/search_information/news/2026-05-27.db')
cursor = conn.execute('SELECT title FROM news_items')
titles = [r[0] for r in cursor.fetchall()]
conn.close()

keywords = [
    '学生', '优惠', '免费', '补贴', '活动', '小米', '华为', '美团', '京东',
    '实习', '校招', '招聘', '宣讲', '内购', '裁员', '融资', 'IPO', '发布',
    '面经', '笔试', '开源', '嵌入式', 'AI', '芯片', '机器人', '自动驾驶',
    '特斯拉', '英伟达', '比亚迪', 'DeepSeek', '大模型', '半导体', '算力'
]

counter = Counter()
for title in titles:
    for kw in keywords:
        if kw in title:
            counter[kw] += 1

print('关键词命中率统计（共 %d 条新闻）:' % len(titles))
print('-' * 40)
for kw, count in counter.most_common():
    print(f'  {kw}: {count} 次 ({count*100//len(titles)}%%)')

print()
print('未命中任何关键词的新闻数量: %d' % (len(titles) - sum(counter.values())))
"''', '关键词命中率统计')

ssh.close()
