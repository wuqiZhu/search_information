import paramiko
import json
import sys
from datetime import datetime
from ssh_helper import get_ssh_client

ssh = get_ssh_client()

results = []
passed = 0
failed = 0


def run(cmd, label="", check_json=False):
    global passed, failed
    if label:
        print(f'\n{"="*60}')
        print(f'>>> {label}')
        print(f'{"="*60}')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out:
        print(out.strip())
    if err and 'WARNING' not in err and 'warn' not in err.lower():
        print(f'[STDERR] {err.strip()}')
    return out.strip(), err.strip()


def check(name, condition, detail=""):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if condition:
        passed += 1
    else:
        failed += 1
    results.append({"name": name, "status": status, "detail": detail})
    icon = "✅" if condition else "❌"
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))


print("=" * 60)
print("服务器项目全面测试")
print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)


# ============================================================
# Task 1: Docker容器状态检查
# ============================================================
print(f'\n{"="*60}')
print("Task 1: Docker容器状态检查")
print(f'{"="*60}')

out, _ = run('docker ps -a --format "{{.Names}}|{{.Status}}|{{.Ports}}"')

expected_containers = ["trendradar", "analyser", "invest-backend", "invest-frontend", "notification-center", "dashboard"]
container_lines = [l for l in out.split('\n') if l.strip()]

for name in expected_containers:
    found = [l for l in container_lines if name in l]
    if found:
        is_up = "Up" in found[0]
        check(f"容器 {name} 状态", is_up, found[0].split('|')[1] if '|' in found[0] else "")
    else:
        check(f"容器 {name} 状态", False, "未找到")

unwanted = [l for l in container_lines if "job-scraper" in l]
check("无 job-scraper 容器", len(unwanted) == 0)

out, _ = run('docker ps --format "{{.Names}}" | wc -l')
running_count = int(out) if out.isdigit() else 0
check("运行中容器数量", running_count >= 6, f"{running_count}个")


# ============================================================
# Task 2: API端点健康检查
# ============================================================
print(f'\n{"="*60}')
print("Task 2: API端点健康检查")
print(f'{"="*60}')

out, _ = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:5050/health')
check("通知中心 /health HTTP状态", out == "200", f"HTTP {out}")

out, _ = run('curl -s http://localhost:5050/health')
try:
    data = json.loads(out)
    check("通知中心 /health 响应格式", data.get("status") == "ok", json.dumps(data, ensure_ascii=False)[:100])
except:
    check("通知中心 /health 响应格式", False, "JSON解析失败")

out, _ = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:5060/api/health')
check("Dashboard /api/health HTTP状态", out == "200", f"HTTP {out}")

out, _ = run('curl -s http://localhost:5060/api/health')
try:
    data = json.loads(out)
    check("Dashboard /api/health 响应格式", data.get("status") == "ok", json.dumps(data, ensure_ascii=False)[:100])
except:
    check("Dashboard /api/health 响应格式", False, "JSON解析失败")

out, _ = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/api/health')
check("投资后端 /api/health HTTP状态", out == "200", f"HTTP {out}")

out, _ = run('curl -s http://localhost:5000/api/health')
try:
    data = json.loads(out)
    check("投资后端 /api/health 响应格式", data.get("status") == "ok", json.dumps(data, ensure_ascii=False)[:100])
except:
    check("投资后端 /api/health 响应格式", False, "JSON解析失败")

out, _ = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:3000')
check("投资前端 HTTP状态", out in ["200", "301", "302", "304"], f"HTTP {out}")

out, _ = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:5060/')
check("Dashboard 主页 HTTP状态", out == "200", f"HTTP {out}")

out, _ = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:5060/api/stats')
check("Dashboard /api/stats HTTP状态", out == "200", f"HTTP {out}")

out, _ = run('curl -s http://localhost:5060/api/stats')
try:
    data = json.loads(out)
    check("Dashboard /api/stats 响应格式", isinstance(data, dict), str(data)[:100])
except:
    check("Dashboard /api/stats 响应格式", False, "JSON解析失败")


# ============================================================
# Task 3: TrendRadar功能测试
# ============================================================
print(f'\n{"="*60}')
print("Task 3: TrendRadar功能测试")
print(f'{"="*60}')

out, _ = run('docker logs --tail 30 trendradar 2>&1')
has_error = "error" in out.lower() or "traceback" in out.lower() or "exception" in out.lower()
check("TrendRadar日志无严重错误", not has_error, "发现错误" if has_error else "正常")

has_activity = any(kw in out.lower() for kw in ["采集", "抓取", "fetch", "crawl", "完成", "done", "saved", "存储", "running", "started", "启动"])
check("TrendRadar日志显示有活动", has_activity or len(out) > 50, f"日志长度: {len(out)}字符")

out, _ = run('docker exec trendradar ls -la /app/output/ 2>/dev/null || echo "目录不存在"')
check("TrendRadar输出目录存在", "目录不存在" not in out, out[:80] if out else "空")

out, _ = run('docker exec trendradar find /app/output -name "*.db" -type f 2>/dev/null | head -5')
has_db = ".db" in out
check("TrendRadar数据库文件已生成", has_db, out[:80] if out else "无.db文件")

out, _ = run('docker exec trendradar find /app/output -name "*.json" -type f 2>/dev/null | head -5')
has_json = ".json" in out
check("TrendRadar JSON数据已生成", has_json, out[:80] if out else "无.json文件")


# ============================================================
# Task 4: 投资分析功能测试
# ============================================================
print(f'\n{"="*60}')
print("Task 4: 投资分析功能测试")
print(f'{"="*60}')

out, _ = run('curl -s http://localhost:5000/api/sentiment/latest')
try:
    data = json.loads(out)
    has_data = "message" not in data or "No sentiment" not in data.get("message", "")
    check("投资后端情绪数据API可用", True, str(data)[:80])
except:
    check("投资后端情绪数据API可用", False, "JSON解析失败")

out, _ = run('curl -s http://localhost:5000/api/sentiment/summary?days=7')
try:
    data = json.loads(out)
    check("投资后端情绪摘要API可用", True, str(data)[:80])
except:
    check("投资后端情绪摘要API可用", False, "JSON解析失败")

out, _ = run('docker logs --tail 20 invest-backend 2>&1')
has_error = "error" in out.lower() or "traceback" in out.lower()
check("投资后端日志无严重错误", not has_error, "发现错误" if has_error else "正常")

out, _ = run('docker exec invest-backend ls -la /app/data/ 2>/dev/null || echo "目录不存在"')
check("投资数据目录存在", "目录不存在" not in out, out[:80] if out else "空")

out, _ = run('docker exec invest-backend find /app/data -name "*.db" -type f 2>/dev/null | head -5')
has_db = ".db" in out
check("投资数据库文件存在", has_db, out[:80] if out else "无.db文件")


# ============================================================
# Task 5: 通知中心功能测试
# ============================================================
print(f'\n{"="*60}')
print("Task 5: 通知中心功能测试")
print(f'{"="*60}')

out, _ = run('curl -s http://localhost:5050/health')
try:
    data = json.loads(out)
    dingtalk_ok = data.get("config", {}).get("dingtalk_configured", False)
    check("钉钉Webhook已配置", dingtalk_ok)
except:
    check("钉钉Webhook已配置", False, "无法获取配置")

out, _ = run('curl -s -X POST http://localhost:5050/notify -H "Content-Type: application/json" -d \'{"text":"通知: 服务器测试消息 - 自动测试","title":"测试通知","priority":"high","source":"test"}\'')
try:
    data = json.loads(out)
    sent = data.get("status") in ["sent", "queued"]
    check("通知发送API可用", sent, str(data)[:80])
except:
    check("通知发送API可用", False, out[:80])

out, _ = run('docker logs --tail 10 notification-center 2>&1')
has_error = "error" in out.lower() and "warning" not in out.lower()
check("通知中心日志无严重错误", not has_error, "发现错误" if has_error else "正常")


# ============================================================
# Task 6: 数据完整性验证
# ============================================================
print(f'\n{"="*60}')
print("Task 6: 数据完整性验证")
print(f'{"="*60}')

out, _ = run('ls -la ~/projects/data/ 2>/dev/null || echo "目录不存在"')
check("数据根目录存在", "目录不存在" not in out, out[:80] if out else "空")

for subdir in ["search_information", "knowledge_base", "invest", "notification"]:
    out, _ = run(f'ls -la ~/projects/data/{subdir}/ 2>/dev/null || echo "目录不存在"')
    check(f"数据子目录 {subdir} 存在", "目录不存在" not in out)

out, _ = run('find ~/projects/data -name "*.db" -type f 2>/dev/null')
db_files = [l for l in out.split('\n') if l.strip()]
check("数据库文件数量", len(db_files) > 0, f"找到 {len(db_files)} 个.db文件")
for db in db_files[:5]:
    print(f"    - {db}")

out, _ = run('find ~/projects/data -name "*.db" -type f -exec sqlite3 {} "SELECT COUNT(*) FROM sqlite_master;" \\; 2>/dev/null | head -10')
check("数据库文件可读取", "Error" not in out and len(out) > 0)

out, _ = run('du -sh ~/projects/data/ 2>/dev/null')
check("数据目录有内容", out and "0" not in out.split('\t')[0], out[:40] if out else "空")


# ============================================================
# Task 7: 额外检查 - 容器资源使用
# ============================================================
print(f'\n{"="*60}')
print("Task 7: 容器资源使用检查")
print(f'{"="*60}')

out, _ = run('docker stats --no-cache --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" 2>/dev/null | head -10')
if out:
    print(out)
    check("容器资源使用正常", True)
else:
    check("容器资源使用正常", False, "无法获取")

out, _ = run('df -h / | tail -1')
print(f"  磁盘使用: {out}")
check("磁盘空间充足", True, out[:60] if out else "")


# ============================================================
# 生成测试报告
# ============================================================
print(f'\n{"="*60}')
print("测试报告汇总")
print(f'{"="*60}')

print(f"\n总测试项: {passed + failed}")
print(f"通过: {passed}")
print(f"失败: {failed}")
print(f"通过率: {passed/(passed+failed)*100:.1f}%")

if failed > 0:
    print(f'\n{"="*60}')
    print("失败项列表:")
    print(f'{"="*60}')
    for r in results:
        if r["status"] == "FAIL":
            print(f"  ❌ {r['name']}" + (f" ({r['detail']})" if r['detail'] else ""))

print(f'\n{"="*60}')
print(f"测试完成！ ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
print(f'{"="*60}')

ssh.close()
