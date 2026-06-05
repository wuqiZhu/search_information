#!/usr/bin/env python3
"""
投资决策系统 - 本地测试脚本
测试项目结构、配置文件、Python依赖声明
"""
import os
import sys
import re
import importlib
from pathlib import Path

GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
NC = '\033[0m'

PROJECT_ROOT = Path(__file__).parent.parent
PROJECTS = {
    'search_information': PROJECT_ROOT / 'search_information',
    'analyse_information': PROJECT_ROOT / 'analyse_information',
    'invest': PROJECT_ROOT / 'invest',
    'Feedback_and_Learning': PROJECT_ROOT / 'Feedback_and_Learning',
}

TOTAL = 0
PASS = 0
FAIL = 0
WARN = 0

def check(condition, msg):
    global TOTAL, PASS, FAIL
    TOTAL += 1
    if condition:
        print(f"  {GREEN}✓{NC} {msg}")
        PASS += 1
    else:
        print(f"  {RED}✗{NC} {msg}")
        FAIL += 1

def warn(msg):
    global WARN
    WARN += 1
    print(f"  {YELLOW}⚠{NC} {msg}")

def section(title):
    print(f"\n{title}")

# ============================================================
# 1. 项目结构检查
# ============================================================
section("1. 项目目录结构")
for name, path in PROJECTS.items():
    check(path.exists(), f"{name}/ 目录存在")

# ============================================================
# 2. Git 仓库检查
# ============================================================
section("2. Git 仓库状态")
for name, path in PROJECTS.items():
    git_dir = path / '.git'
    check(git_dir.exists(), f"{name}/ 有 .git 目录")

# ============================================================
# 3. Dockerfile 检查
# ============================================================
section("3. Dockerfile 检查")
dockerfiles = {
    'search_information': ['TrendRadar/Dockerfile', 'notification_center/Dockerfile', 'dashboard_service/Dockerfile'],
    'analyse_information': ['Dockerfile'],
    'invest': ['Dockerfile'],
    'Feedback_and_Learning': ['Dockerfile'],
}
for proj, files in dockerfiles.items():
    for f in files:
        fp = PROJECTS[proj] / f
        check(fp.exists() and fp.stat().st_size > 0, f"{proj}/{f} 存在且非空")

# ============================================================
# 4. 环境变量模板检查
# ============================================================
section("4. .env.example 检查")
for name, path in PROJECTS.items():
    env_file = path / '.env.example'
    if env_file.exists():
        content = env_file.read_text(encoding='utf-8')
        has_mimo = 'MIMO_API_KEY' in content
        check(has_mimo, f"{name}/.env.example 包含 MIMO_API_KEY")
        if not has_mimo:
            warn(f"{name}/.env.example 缺少 MIMO_API_KEY 配置")
    else:
        check(False, f"{name}/.env.example 文件存在")

# ============================================================
# 5. requirements.txt 检查
# ============================================================
section("5. requirements.txt 依赖检查")

required_deps = {
    'search_information/TrendRadar/requirements.txt': [
        'requests', 'pyyaml', 'beautifulsoup4', 'openai', 'litellm',
        'flask', 'schedule', 'psutil'
    ],
    'analyse_information/requirements.txt': [
        'requests', 'pyyaml', 'flask', 'openai', 'litellm',
        'chromadb', 'tqdm', 'tenacity'
    ],
    'invest/scripts/requirements.txt': [
        'pandas', 'numpy', 'requests', 'pyyaml',
        'openai', 'litellm', 'chromadb', 'tqdm', 'tenacity'
    ],
    'Feedback_and_Learning/invest/scripts/requirements.txt': [
        'pyyaml', 'requests', 'psutil'
    ],
}

for req_path, deps in required_deps.items():
    fp = PROJECT_ROOT / req_path
    if fp.exists():
        content = fp.read_text(encoding='utf-8').lower()
        for dep in deps:
            found = dep.lower() in content
            check(found, f"{req_path} 包含 {dep}")
    else:
        check(False, f"{req_path} 文件存在")

# ============================================================
# 6. 配置文件 API 端点检查
# ============================================================
section("6. API 配置检查")

config_files = {
    'search_information': 'TrendRadar/config/config.yaml',
    'analyse_information': 'analyzer/config.yaml',
}

for proj, cfg in config_files.items():
    fp = PROJECTS[proj] / cfg
    if fp.exists():
        content = fp.read_text(encoding='utf-8')
        check('token-plan-cn.xiaomimimo.com' in content, f"{proj}/{cfg} 端点正确")
        check('mimo-v2.5-pro' in content, f"{proj}/{cfg} 模型名正确")
        check('MIMO_API_KEY' in content, f"{proj}/{cfg} 使用环境变量引用")
        if 'api.deepseek.com' in content:
            warn(f"{proj}/{cfg} 仍包含 deepseek.com 端点")
    else:
        check(False, f"{proj}/{cfg} 文件存在")

# ============================================================
# 7. .gitignore 检查
# ============================================================
section("7. .gitignore 检查")
for name, path in PROJECTS.items():
    gitignore = path / '.gitignore'
    if gitignore.exists():
        content = gitignore.read_text(encoding='utf-8')
        check('.env' in content, f"{name}/.gitignore 排除 .env 文件")
        check('.venv' in content or 'venv' in content, f"{name}/.gitignore 排除虚拟环境")
    else:
        warn(f"{name}/.gitignore 不存在")

# ============================================================
# 结果汇总
# ============================================================
print(f"\n{'='*50}")
print(f"结果: {PASS}/{TOTAL} 通过, {FAIL} 失败, {WARN} 警告")
if FAIL == 0:
    print(f"{GREEN}✓ 本地项目结构正常！{NC}")
else:
    print(f"{RED}✗ {FAIL} 项需要修复{NC}")
print(f"{'='*50}")

sys.exit(1 if FAIL > 0 else 0)
