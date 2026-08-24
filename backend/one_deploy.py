#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
one_deploy-1.py - 一键打包部署脚本

目录结构要求：
    auto_test_project/
    ├── backend/
    │   ├── one_deploy-1.py      <-- 脚本放在这里
    │   ├── config/
    │   │   └── one_deploy_config.json  <-- 配置文件
    │   ├── manage.py
    │   └── requirements.txt
    └── frontend/
        └── package.json

功能：
1. 将 backend 和 frontend 两个目录递归打包成 zip（包含 node_modules）
2. 停止服务器上已运行的后端和前端服务
3. 上传并解压替换项目文件
4. 安装后端依赖（pip3 install -r requirements.txt）
5. 安装前端依赖（yarn install）
6. 启动后端服务（python3 manage.py runserver）
7. 启动前端服务（yarn dev）

使用方法：
    cd backend
    python3 one_deploy-1.py
"""

import os
import sys
import json
import zipfile
import paramiko
import time
import re
import select
from datetime import datetime


DEFAULT_CONFIG = {
    "server_host": "192.168.1.100",
    "server_port": 22,
    "username": "root",
    "password": "your_password_here",
    "private_key_path": None,
    "remote_upload_dir": "/tmp/deploy_uploads",
    "remote_project_dir": "/var/www/myproject",
    "zip_filename": "deploy_package.zip",
    "exclude_patterns": [
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".git",
        ".gitignore",
        ".idea",
        ".vscode",
        "*.log",
        ".env",
        "venv",
        ".venv",
        "one_deploy-1.py",
        "one_deploy.py",
        "config/one_deploy_config.json",
    ],
}


def log(message, level="INFO"):
    """简洁日志输出"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    level_map = {
        "INFO": "🔹",
        "OK": "✅",
        "WARN": "⚠️",
        "ERROR": "❌",
        "STEP": "🚀",
        "STOP": "🛑",
        "INSTALL": "📦",
        "START": "▶️",
    }
    icon = level_map.get(level, "•")
    print(f"[{timestamp}] {icon} {message}", flush=True)


def load_config(script_dir):
    """加载配置文件"""
    config_path = os.path.join(script_dir, "config", "one_deploy_config.json")

    if not os.path.exists(config_path):
        log("配置文件不存在，正在创建默认配置...", "WARN")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        log(f"默认配置已创建: {config_path}", "OK")
        log("请先编辑 config.json 后再运行！", "ERROR")
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        # 合并默认值（兼容旧配置）
        for key, val in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = val
        return config
    except Exception as e:
        log(f"读取配置失败: {e}", "ERROR")
        sys.exit(1)


def validate_config(config):
    """验证配置"""
    required = ["server_host", "server_port", "username", "remote_project_dir"]
    for key in required:
        if not config.get(key):
            log(f"配置项缺失: {key}", "ERROR")
            return False

    has_pwd = config.get("password") and config["password"] != "your_password_here"
    has_key = config.get("private_key_path") and os.path.exists(config["private_key_path"])

    if not has_pwd and not has_key:
        log("请配置密码或私钥！", "ERROR")
        return False

    return True


def should_exclude(rel_path, exclude_patterns):
    """
    检查文件/目录是否应被排除
    :param rel_path: 相对于项目根目录的相对路径
    :param exclude_patterns: 排除模式列表
    """
    parts = rel_path.split(os.sep)
    file_name = os.path.basename(rel_path)

    for pattern in exclude_patterns:
        # 通配符后缀匹配，如 *.pyc
        if pattern.startswith("*"):
            if file_name.endswith(pattern[1:]):
                return True
        # 精确文件名匹配
        elif file_name == pattern:
            return True
        # 目录名匹配（路径中的任意一级目录）
        elif pattern in parts:
            return True
        # 完整相对路径前缀匹配
        elif rel_path.startswith(pattern + os.sep):
            return True

    return False


def create_zip(source_dir, zip_path, exclude_patterns):
    """
    递归打包 backend 和 frontend 两个目录下的所有文件
    """
    log("正在打包...", "STEP")
    log(f"源目录: {source_dir}", "INFO")

    if not os.path.exists(source_dir):
        log(f"源目录不存在: {source_dir}", "ERROR")
        return False

    if os.path.exists(zip_path):
        os.remove(zip_path)
        log("已删除旧zip文件", "INFO")

    file_count = 0
    skip_count = 0
    start_time = time.time()

    # 只处理 backend 和 frontend 两个目录
    target_dirs = ["backend", "frontend"]

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for target_dir in target_dirs:
            dir_path = os.path.join(source_dir, target_dir)

            if not os.path.exists(dir_path):
                log(f"目录不存在，跳过: {target_dir}", "WARN")
                continue

            if not os.path.isdir(dir_path):
                log(f"不是目录，跳过: {target_dir}", "WARN")
                continue

            log(f"处理目录: {target_dir}", "INFO")

            # 递归遍历目录
            for root, dirs, files in os.walk(dir_path):
                # 计算当前目录相对于 source_dir 的相对路径
                rel_root = os.path.relpath(root, source_dir)

                # 过滤掉需要排除的目录
                dirs_to_remove = []
                for d in dirs:
                    rel_dir = os.path.join(rel_root, d)
                    if should_exclude(rel_dir, exclude_patterns):
                        dirs_to_remove.append(d)

                for d in dirs_to_remove:
                    dirs.remove(d)

                # 打包当前目录下的文件
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, source_dir)

                    # 检查是否应被排除
                    if should_exclude(rel_path, exclude_patterns):
                        skip_count += 1
                        continue

                    # 跳过符号链接
                    if os.path.islink(file_path):
                        skip_count += 1
                        continue

                    # 写入zip
                    zipf.write(file_path, rel_path)
                    file_count += 1

    elapsed = time.time() - start_time
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    log(f"打包完成: {file_count} 个文件, 跳过 {skip_count} 个, {size_mb:.1f}MB, 耗时{elapsed:.2f}s", "OK")
    return True


def connect_server(config):
    """连接服务器"""
    log("正在连接服务器...", "STEP")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        if config.get("private_key_path") and os.path.exists(config["private_key_path"]):
            private_key = paramiko.RSAKey.from_private_key_file(config["private_key_path"])
            ssh.connect(
                hostname=config["server_host"],
                port=config["server_port"],
                username=config["username"],
                pkey=private_key,
                timeout=30
            )
        else:
            ssh.connect(
                hostname=config["server_host"],
                port=config["server_port"],
                username=config["username"],
                password=config["password"],
                timeout=30
            )
        log(f"已连接: {config['server_host']}", "OK")
        return ssh
    except Exception as e:
        log(f"连接失败: {e}", "ERROR")
        raise


def upload_file(ssh, local_path, remote_path):
    """上传文件"""
    log("正在上传...", "STEP")

    try:
        sftp = ssh.open_sftp()
        remote_dir = os.path.dirname(remote_path)
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            ssh.exec_command(f"mkdir -p {remote_dir}")

        sftp.put(local_path, remote_path)
        sftp.close()
        log("上传完成", "OK")
        return True
    except Exception as e:
        log(f"上传失败: {e}", "ERROR")
        raise


def exec_cmd(ssh, cmd, show_output=False, timeout=30):
    """
    执行简单远程命令（适用于短命令，如 ps/kill/ls 等）。
    使用 exec_command，速度快。
    """
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout, get_pty=False)

    # 等待命令完成
    exit_status = stdout.channel.recv_exit_status()

    out = stdout.read().decode('utf-8', errors='ignore').strip()
    err = stderr.read().decode('utf-8', errors='ignore').strip()

    if show_output and out:
        print(out)

    if exit_status == 0:
        return True, out

    real_err = [line for line in err.split('\n')
                if line
                and 'warning' not in line.lower()
                and 'inflating' not in line.lower()
                and 'already satisfied' not in line.lower()
                and 'no such process' not in line.lower()
                and 'no matches found' not in line.lower()
                and 'deprecated' not in line.lower()
                and 'audit' not in line.lower()
                and 'funding' not in line.lower()]

    if real_err:
        return False, '\n'.join(real_err)

    return True, out


def exec_cmd_with_pty(ssh, cmd, timeout=600, show_output=True):
    """
    执行需要 TTY 的命令（如 pip install / yarn install）。
    使用 exec_command + get_pty=True，stdout/stderr 合并到 stdout。
    通过 select 非阻塞轮询读取输出，避免 stdout 缓冲区满导致阻塞。
    """
    log(f"执行命令: {cmd[:80]}...", "INFO")

    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout, get_pty=True)
    channel = stdout.channel

    out_data = []
    start_time = time.time()
    last_output_time = time.time()

    while True:
        current_time = time.time()

        # 整体超时检查
        if current_time - start_time > timeout:
            channel.close()
            return False, f"命令执行超时 (>{timeout}s): {cmd}"

        # 输出停滞检测（180秒无新输出则判定卡死）
        if current_time - last_output_time > 180:
            channel.close()
            return False, f"命令输出停滞超过180秒，可能已卡死: {cmd}"

        # 使用 select 等待数据可读
        readable, _, _ = select.select([channel], [], [], 0.5)

        if readable:
            if channel.recv_ready():
                data = channel.recv(8192).decode('utf-8', errors='ignore')
                if data:
                    out_data.append(data)
                    if show_output:
                        print(data, end='', flush=True)
                    last_output_time = current_time

        # 检查命令是否已退出
        if channel.exit_status_ready():
            # 读取剩余输出
            while channel.recv_ready():
                data = channel.recv(8192).decode('utf-8', errors='ignore')
                if data:
                    out_data.append(data)
                    if show_output:
                        print(data, end='', flush=True)
                    last_output_time = current_time
            break

        # 如果没有数据且通道未关闭，短暂休眠
        if not readable:
            time.sleep(0.1)

    exit_status = channel.recv_exit_status()
    channel.close()

    out = ''.join(out_data).strip()

    if exit_status == 0:
        return True, out

    # 过滤非错误信息
    real_err = [line for line in out.split('\n')
                if line
                and 'warning' not in line.lower()
                and 'inflating' not in line.lower()
                and 'already satisfied' not in line.lower()
                and 'no such process' not in line.lower()
                and 'no matches found' not in line.lower()
                and 'deprecated' not in line.lower()
                and 'audit' not in line.lower()
                and 'funding' not in line.lower()
                and 'info' not in line.lower()]

    if real_err:
        return False, '\n'.join(real_err)

    return True, out


def get_server_env_path(ssh):
    """
    获取服务器上的完整 PATH。

    修复：不 source ~/.zshrc（避免触发 ssh-add 等交互式命令），
    而是直接读取当前 shell 的 PATH，然后手动追加常见路径。
    """
    # 方案1: 直接获取当前 PATH（不加载任何配置文件）
    ok, path_out = exec_cmd_with_pty(ssh, "echo $PATH", timeout=10, show_output=False)
    if ok and path_out:
        lines = [l.strip() for l in path_out.split('\n') if l.strip()]
        if lines:
            base_path = lines[-1]
        else:
            base_path = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    else:
        base_path = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

    # 手动追加常见的 node/yarn 路径（这些路径通常由 .zshrc/.bashrc 添加）
    # 注意：优先追加用户特定的路径，确保它们排在系统路径前面
    common_paths = [
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/opt/homebrew/opt/node/bin",
        "~/.yarn/bin",
        "~/.local/bin",
        "/usr/local/opt/yarn/bin",
        "/usr/local/opt/node/bin",
        "/usr/local/bin",
        "/usr/local/sbin",
    ]

    # 合并 PATH，去重，用户路径在前
    all_paths = []
    for p in common_paths:
        expanded = os.path.expanduser(p)
        if expanded not in all_paths:
            all_paths.append(expanded)

    # 追加基础 PATH 中的路径
    for p in base_path.split(':'):
        if p and p not in all_paths:
            all_paths.append(p)

    merged_path = ':'.join(all_paths)
    return merged_path


def get_yarn_cmd(ssh):
    """
    获取 yarn 命令路径。
    修复：不仅查找路径，还验证文件是否真实存在且可执行。
    """
    # 优先检查常见绝对路径（避免 PATH 顺序问题）
    priority_paths = [
        "/opt/homebrew/bin/yarn",
        "/usr/local/bin/yarn",
        "/usr/bin/yarn",
        "~/.yarn/bin/yarn",
        "~/.local/bin/yarn",
        "/usr/local/opt/yarn/bin/yarn",
    ]

    for test_path in priority_paths:
        expanded = os.path.expanduser(test_path)
        ok, _ = exec_cmd_with_pty(ssh, f"test -x {expanded} && echo {expanded}", timeout=10, show_output=False)
        if ok:
            lines = [l.strip() for l in _.split('\n') if l.strip()]
            if lines and lines[-1] == expanded:
                return expanded

    # 如果绝对路径都找不到，尝试用 command -v（让 PATH 决定）
    ok, path = exec_cmd_with_pty(ssh, "command -v yarn", timeout=10, show_output=False)
    if ok and path:
        lines = [l.strip() for l in path.split('\n') if l.strip()]
        if lines and '/' in lines[-1]:
            # 验证找到的路径是否真实可执行
            found_path = lines[-1]
            ok2, _ = exec_cmd_with_pty(ssh, f"test -x {found_path}", timeout=10, show_output=False)
            if ok2:
                return found_path

    return None


def get_node_cmd(ssh):
    """
    获取 node 命令的绝对路径。
    yarn 是一个 shell 脚本，内部通过 /usr/bin/env node 调用 node，
    如果 PATH 不对就会报 'env: node: No such file or directory'。
    因此需要找到 node 的绝对路径，后续启动时显式注入 PATH。
    """
    priority_paths = [
        "/opt/homebrew/bin/node",
        "/opt/homebrew/opt/node/bin/node",
        "/usr/local/bin/node",
        "/usr/bin/node",
        "~/.nvm/versions/node/*/bin/node",
        "~/.local/bin/node",
    ]

    for test_path in priority_paths:
        expanded = os.path.expanduser(test_path)
        # 支持通配符路径（如 nvm）
        if '*' in expanded:
            ok, out = exec_cmd_with_pty(ssh, f"ls {expanded} 2>/dev/null | head -1", timeout=10, show_output=False)
            if ok and out.strip():
                expanded = out.strip().split('\n')[-1].strip()
        ok, _ = exec_cmd_with_pty(ssh, f"test -x {expanded} && echo {expanded}", timeout=10, show_output=False)
        if ok:
            lines = [l.strip() for l in _.split('\n') if l.strip()]
            if lines and lines[-1] == expanded:
                return expanded

    # fallback: 用 command -v
    ok, path = exec_cmd_with_pty(ssh, "command -v node", timeout=10, show_output=False)
    if ok and path:
        lines = [l.strip() for l in path.split('\n') if l.strip()]
        if lines and '/' in lines[-1]:
            found_path = lines[-1]
            ok2, _ = exec_cmd_with_pty(ssh, f"test -x {found_path}", timeout=10, show_output=False)
            if ok2:
                return found_path

    return None


def stop_services(ssh, project_dir):
    """
    停止服务器上已运行的后端和前端服务
    后端服务统一通过 service_manager.sh 管理（django-runserver / task-scheduler / mock-proxy）
    前端服务独立管理
    """
    log("正在停止旧服务...", "STOP")

    backend_dir = f"{project_dir}/backend"
    frontend_dir = f"{project_dir}/frontend"

    # 1. 使用 service_manager.sh 停止所有后端服务
    log("通过 service_manager.sh 停止后端服务...", "INFO")
    ok, out = exec_cmd(ssh, f"cd {backend_dir} && bash service_manager.sh stop")
    if not ok:
        log(f"service_manager.sh stop 执行异常: {out}", "WARN")
    else:
        log("后端服务已通过 service_manager.sh 停止", "OK")

    # 2. 停止前端 yarn dev / npx vite / node vite
    log("查找前端服务进程...", "INFO")
    ok, pids = exec_cmd(ssh, f"ps aux | grep -E '(yarn dev|npx vite|node.*vite)' | grep -v grep | awk '{{print $2}}'")
    if pids:
        for pid in pids.strip().split('\n'):
            pid = pid.strip()
            if pid:
                log(f"停止前端进程 (PID: {pid})", "INFO")
                exec_cmd(ssh, f"kill -9 {pid} 2>/dev/null || true")
    else:
        log("未找到运行中的前端服务", "INFO")

    # 3. 额外清理：停止项目目录下所有残留的 node 进程（防止漏网之鱼）
    log("清理残留进程...", "INFO")
    exec_cmd(ssh, f"ps aux | grep '{project_dir}' | grep -E '(node|yarn)' | grep -v grep | awk '{{print $2}}' | xargs -r kill -9 2>/dev/null || true")

    # 等待进程完全退出
    time.sleep(2)
    log("旧服务已停止", "OK")


def check_frontend_started(ssh, project_dir, max_wait=5):
    """
    检查前端服务是否真正启动成功。
    修复：不仅检测进程名，还检测日志内容和项目目录下的 node 进程。

    Vite 启动时进程名可能是 node/vite/npx，而不是 yarn dev，
    所以需要用多种方式验证。
    """
    frontend_dir = f"{project_dir}/frontend"

    for attempt in range(max_wait):
        time.sleep(1)

        # 方法1: 检查日志中是否有 Vite 成功启动标志
        ok, log_content = exec_cmd(ssh, f"cat /tmp/frontend.log 2>/dev/null | tail -20", show_output=False)
        if ok and log_content:
            # Vite 成功启动的标志
            success_markers = [
                "ready in",
                "Local:",
                "Network:",
                "VITE",
                "Vite",
            ]
            for marker in success_markers:
                if marker in log_content:
                    return True, f"日志检测到启动成功标志: {marker}"

        # 方法2: 检查项目 frontend 目录下是否有 node 进程
        ok, pids = exec_cmd(ssh, f"ps aux | grep '{frontend_dir}' | grep -E 'node' | grep -v grep | awk '{{print $2}}'")
        if pids and pids.strip():
            return True, f"检测到前端 node 进程 (PID: {pids.strip().split()[0]})"

        # 方法3: 检查是否有 vite 相关进程
        ok, pids = exec_cmd(ssh, f"ps aux | grep -E 'vite' | grep -v grep | awk '{{print $2}}'")
        if pids and pids.strip():
            return True, f"检测到 vite 进程 (PID: {pids.strip().split()[0]})"

    return False, "未检测到前端启动成功标志"


def deploy_on_server(ssh, config):
    """在服务器上部署"""
    zip_path = os.path.join(config["remote_upload_dir"], config["zip_filename"])
    project_dir = config["remote_project_dir"]
    backend_dir = f"{project_dir}/backend"
    frontend_dir = f"{project_dir}/frontend"

    log("正在部署...", "STEP")

    # 1. 停止旧服务
    stop_services(ssh, project_dir)

    # 2. 备份 & 解压替换
    log("正在替换文件...", "STEP")
    ok, out = exec_cmd(ssh, f"""
        setopt +o nomatch 2>/dev/null || true
        mkdir -p {project_dir}
    """)
    if not ok:
        log(f"创建目录失败: {out}", "ERROR")
        return False

    ok, out = exec_cmd(ssh, f"""
        setopt +o nomatch 2>/dev/null || true
        if [ -d {project_dir} ] && [ -n "$(ls -A {project_dir} 2>/dev/null)" ]; then
            backup_dir='{project_dir}_backup_$(date +%Y%m%d_%H%M%S)'
            cp -r {project_dir} "$backup_dir"
            echo "已备份: $backup_dir"
            ls -td {project_dir}_backup_* 2>/dev/null | tail -n +4 | xargs -r rm -rf
        fi
    """)
    if not ok:
        log(f"备份失败: {out}", "ERROR")
        return False

    # 解压到新临时目录
    ok, out = exec_cmd(ssh, f"unzip -o {zip_path} -d {project_dir}_temp")
    if not ok:
        log(f"解压失败: {out}", "ERROR")
        return False

    # 清空旧文件并移动新文件
    ok, out = exec_cmd(ssh, f"""
        setopt +o nomatch 2>/dev/null || true
        find {project_dir} -mindepth 1 -maxdepth 1 -exec rm -rf {{}} + 2>/dev/null
        find {project_dir}_temp -mindepth 1 -maxdepth 1 -exec mv -f {{}} {project_dir}/ \; 2>/dev/null
        rm -rf {project_dir}_temp {zip_path}
    """)
    if not ok:
        log(f"文件替换失败: {out}", "ERROR")
        return False
    log("文件替换完成", "OK")

    # =========================================================================
    # Phase 2: 环境检测（在安装依赖前完成，不影响后续安装流程）
    # =========================================================================
    log("正在检测服务器环境...", "INFO")

    # 获取服务器 PATH
    env_path = get_server_env_path(ssh)
    if env_path:
        log(f"服务器 PATH 已获取", "INFO")
    else:
        log("无法获取服务器 PATH，使用默认环境", "WARN")

    # 构建前端需要的 PATH 前缀
    path_prefix = f"export PATH='{env_path}'; " if env_path else ""

    # 获取 yarn
    log("正在检测 yarn...", "INFO")
    yarn_cmd = get_yarn_cmd(ssh)
    if yarn_cmd:
        log(f"检测到 yarn: {yarn_cmd}", "INFO")
    else:
        log("未检测到 yarn，将使用 npm", "WARN")

    # 获取 node
    log("正在检测 node...", "INFO")
    node_cmd = get_node_cmd(ssh)
    if node_cmd:
        log(f"检测到 node: {node_cmd}", "INFO")
    else:
        log("未检测到 node，前端启动可能会失败", "WARN")

    # =========================================================================
    # Phase 3: 安���依赖（两端都完成才进入下一阶段）
    # =========================================================================
    log("=" * 40, "INFO")
    log("Phase 3: 安装依赖", "INSTALL")
    log("=" * 40, "INFO")

    # 3a. 安装后端依赖
    backend_deps_ok = False
    log("正在安装后端依赖...", "INSTALL")
    ok, out = exec_cmd_with_pty(
        ssh,
        f"cd {backend_dir} && PIP_BIN=$(test -f venv/bin/pip && echo venv/bin/pip || echo pip3) && $PIP_BIN install -r requirements.txt",
        timeout=300,
        show_output=True
    )
    if not ok:
        log(f"后端依赖安装失败: {out}", "ERROR")
        return False
    backend_deps_ok = True
    log("后端依赖安装完成", "OK")

    # 3b. 安装前端依赖
    frontend_deps_ok = False
    log("正在安装前端依赖...", "INSTALL")

    if yarn_cmd:
        install_cmd = f"{path_prefix}cd {frontend_dir} && {yarn_cmd} install"
        ok, out = exec_cmd_with_pty(ssh, install_cmd, timeout=600, show_output=True)
        if not ok:
            log("首次安装失败，尝试强制重新安装...", "WARN")
            install_cmd = f"{path_prefix}cd {frontend_dir} && {yarn_cmd} install --force"
            ok, out = exec_cmd_with_pty(ssh, install_cmd, timeout=600, show_output=True)
    else:
        install_cmd = f"{path_prefix}cd {frontend_dir} && npm install"
        ok, out = exec_cmd_with_pty(ssh, install_cmd, timeout=600, show_output=True)

    if not ok:
        log(f"前端依赖安装失败: {out}", "ERROR")
        return False
    frontend_deps_ok = True
    log("前端依赖安装完成", "OK")

    # 3c. 依赖安装确认点：两端都完成才继续
    if not (backend_deps_ok and frontend_deps_ok):
        log("依赖安装未全部完成，终止启动服务", "ERROR")
        return False
    log("✅ 后端 + 前端依赖均已安装完成", "OK")

    # =========================================================================
    # Phase 4: 启动服务
    # =========================================================================
    log("=" * 40, "INFO")
    log("Phase 4: 启动服务", "START")
    log("=" * 40, "INFO")

    # 4a. 通过 service_manager.sh 启动所有后端服务（django-runserver / task-scheduler / mock-proxy）
    log("正在通过 service_manager.sh 启动所有后端服务...", "START")
    ok, out = exec_cmd_with_pty(
        ssh,
        f"cd {backend_dir} && bash service_manager.sh start",
        timeout=120,
        show_output=True
    )
    if not ok:
        log("service_manager.sh start 返回异常，部分服务启动失败，正在检查详情...", "WARN")
    else:
        log("所有后端服务已通过 service_manager.sh 启动", "OK")

    # 4b. 启动后验证：逐个检查服务状态，失败的打印日志尾部
    log("正在验证各服务启动状态...", "INFO")
    status_ok, status_out = exec_cmd(ssh, f"cd {backend_dir} && bash service_manager.sh status", show_output=True)
    if status_ok:
        services_to_check = [
            ("django-runserver", "logs/django_runserver.log"),
            ("task-scheduler", "logs/task_scheduler.log"),
            ("mock-proxy", "logs/mock_proxy.log"),
        ]
        for svc_name, log_file in services_to_check:
            svc_log_path = f"{backend_dir}/{log_file}"
            ok2, pid_check = exec_cmd(
                ssh,
                f"cd {backend_dir} && bash service_manager.sh status 2>/dev/null | grep '{svc_name}'"
            )
            if ok2 and pid_check:
                if "未运行" in pid_check or "已失效" in pid_check or "端口残留" in pid_check:
                    log(f"{svc_name}: 启动失败，查看日志尾部:", "ERROR")
                    ok3, log_tail = exec_cmd(ssh, f"tail -30 {svc_log_path} 2>/dev/null || echo '(日志文件为空或不存在)'")
                    if ok3 and log_tail:
                        for line in log_tail.split('\n'):
                            if line.strip():
                                log(f"  [{svc_name}] {line.strip()}", "WARN")
                else:
                    log(f"{svc_name}: 运行正常", "OK")
    log("服务状态验证完成", "INFO")

    # 4c. 启动前端服务（后台运行）
    log("正在启动前端服务...", "START")

    # 构建环境变量前缀：PATH + NODE_PATH
    env_exports = []
    if env_path:
        env_exports.append(f"export PATH='{env_path}'")
    if node_cmd:
        node_dir = os.path.dirname(node_cmd)
        if node_dir and node_dir not in (env_path or ""):
            env_exports.append(f"export PATH='{node_dir}':$PATH")
        env_exports.append(f"export NODE_PATH='{node_dir}'")

    env_prefix = "; ".join(env_exports)
    if env_prefix:
        env_prefix += "; "

    if yarn_cmd:
        start_cmd = f"{env_prefix}cd {frontend_dir} && nohup {yarn_cmd} dev > /tmp/frontend.log 2>&1 &"
    else:
        start_cmd = f"{env_prefix}cd {frontend_dir} && nohup npm run dev > /tmp/frontend.log 2>&1 &"

    ok, err = exec_cmd(ssh, start_cmd)
    if not ok:
        log(f"前端启动异常: {err}", "WARN")
    else:
        started, reason = check_frontend_started(ssh, project_dir, max_wait=5)
        if started:
            log(f"前端已启动 ({reason})", "OK")
        else:
            log(f"前端启动可能失败: {reason}，请检查 /tmp/frontend.log", "WARN")

    log("部署完成", "OK")
    return True


def main():
    log("=" * 40, "INFO")
    log("一键部署启动", "STEP")
    log("=" * 40, "INFO")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    log(f"脚本目录: {script_dir}", "INFO")
    log(f"项目根目录: {project_root}", "INFO")

    config = load_config(script_dir)
    if not validate_config(config):
        sys.exit(1)

    # 打包
    zip_path = os.path.join(script_dir, config["zip_filename"])
    try:
        success = create_zip(project_root, zip_path, config["exclude_patterns"])
        if not success:
            sys.exit(1)
    except Exception as e:
        log(f"打包失败: {e}", "ERROR")
        sys.exit(1)

    # 连接 & 上传 & 部署
    ssh = None
    deploy_success = False
    try:
        ssh = connect_server(config)
        remote_zip_path = os.path.join(config["remote_upload_dir"], config["zip_filename"])
        upload_file(ssh, zip_path, remote_zip_path)
        deploy_success = deploy_on_server(ssh, config)
    except Exception as e:
        import traceback
        log(f"部署失败: {e}", "ERROR")
        log("详细错误信息:", "ERROR")
        traceback.print_exc()
        if ssh:
            ssh.close()
        sys.exit(1)
    finally:
        if ssh:
            ssh.close()

    # 清理本地 zip
    try:
        os.remove(zip_path)
    except Exception:
        pass

    # 根据部署结果输出不同的结束日志
    if deploy_success:
        log("=" * 40, "INFO")
        log("全部完成", "OK")
        log("=" * 40, "INFO")
    else:
        log("=" * 40, "INFO")
        log("部署未完成，存在错误", "ERROR")
        log("=" * 40, "INFO")
        sys.exit(1)


if __name__ == "__main__":
    main()
