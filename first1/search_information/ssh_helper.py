# -*- coding: utf-8 -*-
"""SSH 连接助手 - 从环境变量读取凭证"""

import os
import sys
import paramiko


def get_ssh_client(host=None, timeout=10):
    """创建 SSH 客户端，凭证从环境变量读取"""
    host = host or os.environ.get('SSH_HOST', '188.166.249.182')
    user = os.environ.get('SSH_USER', 'root')
    password = os.environ.get('SSH_PASS')

    if not password:
        print("Error: 请设置 SSH_PASS 环境变量")
        sys.exit(1)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password, timeout=timeout)
    return ssh
