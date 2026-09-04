#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
git_deploy.py - 基于 git 的一键部署脚本

目录结构要求：
    auto_test_project/
    ├── backend/
    │   ├── git_deploy.py            <-- 脚本放在这里
    │   ├── config/
    │   │   └── one_deploy_config.json  <-- 配置文件（复用 one_deploy 的配置）
    │   ├── manage.py
    │   └── requirements.txt
    └── frontend/
        └── package.json

部署流程：
1. 登录服务器（SSH）
2. 进入部署项目目录
3. 停止已运行的后端和前端服务
4. 通过 git 拉取远程代码更新（不删除本地文件；未跟踪的 page_config.json / logs / venv / node_modules 会保留）
5. 安装后端依赖（pip3 install -r requirements.txt）
6. 安装前端依赖（yarn install / npm install）
7. 启动后端服务（service_manager.sh start）
8. 启动前端服务（yarn dev / npm run dev）

使用方法：
    cd backend
    python3 git_deploy.py              # 完整部署（停服务 → 拉代码 → 装依赖 → 启服务）
    python3 git_deploy.py --hot        # 热更（仅登录服务器拉取 git 代码更新，更新成功即结束）
    python3 git_deploy.py --hot --fe   # 热更 + 重启前端（拉取 git 代码后重启前端服务）
    python3 git_deploy.py --hot --rd   # 热更 + 重启后端（拉取 git 代码后重启后端服务）

参数说明：
    --hot / --hot-update  热更模式：不停服务、不安装依赖，
                          仅通过 git 拉取远程代码，更新成功后即结束。
    --fe                  配合 --hot 使用：拉取 git 代码后，重启前端服务
                          （yarn dev / npm run dev），不影响后端服务，不安装依赖。
    --rd                  配合 --hot 使用：拉取 git 代码后，通过 service_manager.sh
                          重启后端服务，不影响前端服务，不安装依赖。
"""

import argparse
import os
import sys
import json
import time
import select
import paramiko
from datetime import datetime


DEFAULT_CONFIG = {
    "server_host": "192.168.1.100",
    "server_port": 22,
    "username": "root",
    "password": "your_password_here",
    "private_key_path": None,
    "remote_project_dir": "/var/www/myproject",
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
    """加载配置文件（复用 one_deploy.py 的 one_deploy_config.json）"""
    config_path = os.path.join(script_dir, "config", "one_deploy_config.json")

    if not os.path.exists(config_path):
        log("配置文件不存在，正在创建默认配置...", "WARN")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        log(f"默认配置已创建: {config_path}", "OK")
        log("请先编辑 config/one_deploy_config.json 后再运行！", "ERROR")
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


def exec_cmd(ssh, cmd, show_output=False, timeout=30):
    """
    执行简单远程命令（适用于短命令，如 ps/kill/ls 等）。
    """
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout, get_pty=False)

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
    执行需要 TTY 的命令（如 pip install / yarn install / git pull）。
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
            while channel.recv_ready():
                data = channel.recv(8192).decode('utf-8', errors='ignore')
                if data:
                    out_data.append(data)
                    if show_output:
                        print(data, end='', flush=True)
                    last_output_time = current_time
            break

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
    """
    ok, path_out = exec_cmd_with_pty(ssh, "echo $PATH", timeout=10, show_output=False)
    if ok and path_out:
        lines = [l.strip() for l in path_out.split('\n') if l.strip()]
        if lines:
            base_path = lines[-1]
        else:
            base_path = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    else:
        base_path = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

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

    all_paths = []
    for p in common_paths:
        expanded = os.path.expanduser(p)
        if expanded not in all_paths:
            all_paths.append(expanded)

    for p in base_path.split(':'):
        if p and p not in all_paths:
            all_paths.append(p)

    return ':'.join(all_paths)


def get_yarn_cmd(ssh):
    """获取 yarn 命令路径。"""
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

    ok, path = exec_cmd_with_pty(ssh, "command -v yarn", timeout=10, show_output=False)
    if ok and path:
        lines = [l.strip() for l in path.split('\n') if l.strip()]
        if lines and '/' in lines[-1]:
            found_path = lines[-1]
            ok2, _ = exec_cmd_with_pty(ssh, f"test -x {found_path}", timeout=10, show_output=False)
            if ok2:
                return found_path

    return None


def get_node_cmd(ssh):
    """获取 node 命令的绝对路径。"""
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
        if '*' in expanded:
            ok, out = exec_cmd_with_pty(ssh, f"ls {expanded} 2>/dev/null | head -1", timeout=10, show_output=False)
            if ok and out.strip():
                expanded = out.strip().split('\n')[-1].strip()
        ok, _ = exec_cmd_with_pty(ssh, f"test -x {expanded} && echo {expanded}", timeout=10, show_output=False)
        if ok:
            lines = [l.strip() for l in _.split('\n') if l.strip()]
            if lines and lines[-1] == expanded:
                return expanded

    ok, path = exec_cmd_with_pty(ssh, "command -v node", timeout=10, show_output=False)
    if ok and path:
        lines = [l.strip() for l in path.split('\n') if l.strip()]
        if lines and '/' in lines[-1]:
            found_path = lines[-1]
            ok2, _ = exec_cmd_with_pty(ssh, f"test -x {found_path}", timeout=10, show_output=False)
            if ok2:
                return found_path

    return None


def stop_frontend(ssh, project_dir):
    """停止前端服务进程（yarn dev / npx vite / node vite）。"""
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

    # 额外清理：停止项目目录下所有残留的 node 进程
    log("清理残留进程...", "INFO")
    exec_cmd(ssh, f"ps aux | grep '{project_dir}' | grep -E '(node|yarn)' | grep -v grep | awk '{{print $2}}' | xargs -r kill -9 2>/dev/null || true")

    # 等待进程完全退出
    time.sleep(2)
    log("前端服务已停止", "OK")


def stop_backend_service(ssh, project_dir):
    """
    仅停止后端服务（通过 service_manager.sh 管理 django-runserver / task-scheduler / mock-proxy），
    不影响前端服务。
    """
    backend_dir = f"{project_dir}/backend"

    log("通过 service_manager.sh 停止后端服务...", "INFO")
    ok, out = exec_cmd(ssh, f"cd {backend_dir} && bash service_manager.sh stop")
    if not ok:
        log(f"service_manager.sh stop 执行异常: {out}", "WARN")
    else:
        log("后端服务已通过 service_manager.sh 停止", "OK")


def start_backend_service(ssh, project_dir):
    """仅启动后端服务（通过 service_manager.sh），不影响前端服务。"""
    backend_dir = f"{project_dir}/backend"

    log("正在通过 service_manager.sh 启动后端服务...", "START")
    ok, out = exec_cmd_with_pty(
        ssh,
        f"cd {backend_dir} && bash service_manager.sh start",
        timeout=120,
        show_output=True,
    )
    if not ok:
        log("service_manager.sh start 返回异常，部分服务启动失败，正在检查详情...", "WARN")
    else:
        log("所有后端服务已通过 service_manager.sh 启动", "OK")


def stop_services(ssh, project_dir):
    """
    停止服务器上已运行的后端和前端服务。
    后端服务统一通过 service_manager.sh 管理（django-runserver / task-scheduler / mock-proxy），
    前端服务独立管理。
    """
    log("正在停止旧服务...", "STOP")

    # 1. 使用 service_manager.sh 停止所有后端服务
    stop_backend_service(ssh, project_dir)

    # 2. 停止前端服务
    stop_frontend(ssh, project_dir)

    log("旧服务已停止", "OK")


def git_pull(ssh, config):
    """
    通过 git 拉取远程代码更新项目。

    不删除本地文件：git fetch + reset --hard 只会更新「已跟踪」的文件，
    未跟踪的 page_config.json / logs / venv / node_modules 等会原样保留。
    """
    project_dir = config["remote_project_dir"]
    branch = "master"

    log("正在通过 git 拉取远程代码（仅 master 分支）...", "STEP")

    # 确认目录存在且是 git 仓库
    ok, out = exec_cmd(ssh, f"cd {project_dir} && git rev-parse --is-inside-work-tree")
    if not ok:
        log(f"目录不存在或不是 git 仓库: {project_dir}", "ERROR")
        log("请先在服务器上 clone 该仓库，例如：", "WARN")
        log(f"  git clone <仓库地址> {project_dir}", "WARN")
        return False

    # 拉取并强制同步到远程分支
    ok, out = exec_cmd_with_pty(
        ssh,
        f"cd {project_dir} && git fetch origin && git reset --hard origin/{branch}",
        timeout=300,
        show_output=True,
    )
    if not ok:
        log(f"git 拉取失败: {out}", "ERROR")
        return False

    log(f"git 已更新到 origin/{branch}", "OK")
    return True


def hot_update_on_server(ssh, config):
    """
    热更：仅通过 git 拉取远程代码更新。
    不停服务、不安装依赖、不重启服务，git 更新成功即结束。
    """
    log("正在执行热更（仅更新 git 代码）...", "STEP")
    if not git_pull(ssh, config):
        return False
    log("热更完成", "OK")
    return True


def check_frontend_started(ssh, project_dir, max_wait=5):
    """
    检查前端服务是否真正启动成功。
    """
    frontend_dir = f"{project_dir}/frontend"

    for attempt in range(max_wait):
        time.sleep(1)

        # 方法1: 检查日志中是否有 Vite 成功启动标志
        ok, log_content = exec_cmd(ssh, f"cat /tmp/frontend.log 2>/dev/null | tail -20", show_output=False)
        if ok and log_content:
            success_markers = ["ready in", "Local:", "Network:", "VITE", "Vite"]
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


def start_frontend(ssh, config):
    """启动前端服务（yarn dev / npm run dev，后台运行）。"""
    project_dir = config["remote_project_dir"]
    frontend_dir = f"{project_dir}/frontend"

    log("正在启动前端服务...", "START")

    env_path = get_server_env_path(ssh)
    node_cmd = get_node_cmd(ssh)
    yarn_cmd = get_yarn_cmd(ssh)

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
        return

    started, reason = check_frontend_started(ssh, project_dir, max_wait=5)
    if started:
        log(f"前端已启动 ({reason})", "OK")
    else:
        log(f"前端启动可能失败: {reason}，请检查 /tmp/frontend.log", "WARN")


def restart_frontend_on_server(ssh, config):
    """
    仅重启前端：拉取 git 代码后，只重启前端服务（不��后端、不装依赖）。
    对应参数：--hot --fe
    """
    log("正在拉取代码并重启前端服务...", "STEP")
    if not git_pull(ssh, config):
        return False

    project_dir = config["remote_project_dir"]
    stop_frontend(ssh, project_dir)
    start_frontend(ssh, config)

    log("前端重启完成", "OK")
    return True


def restart_backend_on_server(ssh, config):
    """
    仅重启后端：拉取 git 代码后，只重启后端服务（不停前端、不装依赖）。
    对应参数：--hot --rd
    """
    log("正在拉取代码并重启后端服务...", "STEP")
    if not git_pull(ssh, config):
        return False

    project_dir = config["remote_project_dir"]
    stop_backend_service(ssh, project_dir)
    start_backend_service(ssh, project_dir)

    log("后端重启完成", "OK")
    return True


def restart_both_on_server(ssh, config):
    """
    同时重启前后端：拉取 git 代码后，重启前端与后端服务（不装依赖）。
    对应参数：--hot --fe --rd
    """
    log("正在拉取代码并重启前后端服务...", "STEP")
    if not git_pull(ssh, config):
        return False

    project_dir = config["remote_project_dir"]
    stop_backend_service(ssh, project_dir)
    stop_frontend(ssh, project_dir)
    start_backend_service(ssh, project_dir)
    start_frontend(ssh, config)

    log("前后端重启完成", "OK")
    return True


def deploy_on_server(ssh, config):
    """在服务器上部署"""
    project_dir = config["remote_project_dir"]
    backend_dir = f"{project_dir}/backend"
    frontend_dir = f"{project_dir}/frontend"

    log("正在部署...", "STEP")

    # 1. 停止旧服务
    stop_services(ssh, project_dir)

    # 2. 通过 git 拉取远程代码
    if not git_pull(ssh, config):
        return False

    # =========================================================================
    # Phase 2: 环境检测（在安装依赖前完成）
    # =========================================================================
    log("正在检测服务器环境...", "INFO")

    env_path = get_server_env_path(ssh)
    if env_path:
        log("服务器 PATH 已获取", "INFO")
    else:
        log("无法获取服务器 PATH，使用默认环境", "WARN")

    path_prefix = f"export PATH='{env_path}'; " if env_path else ""

    log("正在检测 yarn...", "INFO")
    yarn_cmd = get_yarn_cmd(ssh)
    if yarn_cmd:
        log(f"检测到 yarn: {yarn_cmd}", "INFO")
    else:
        log("未检测到 yarn，将使用 npm", "WARN")

    log("正在检测 node...", "INFO")
    node_cmd = get_node_cmd(ssh)
    if node_cmd:
        log(f"检测到 node: {node_cmd}", "INFO")
    else:
        log("未检测到 node，前端启动可能会失败", "WARN")

    # =========================================================================
    # Phase 3: 安装依赖（两端都完成才进入下一阶段）
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

    # 4a. 通过 service_manager.sh 启动所有后端服务
    start_backend_service(ssh, project_dir)

    # 4b. 启动后验证：逐个检查服务状态
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
    start_frontend(ssh, config)

    log("部署完成", "OK")
    return True


def parse_args():
    """解析命令行参数：默认完整部署；--hot 为热更模式，可配合 --fe / --rd 重启对应服务。"""
    parser = argparse.ArgumentParser(description="基于 git 的一键部署脚本")
    parser.add_argument(
        "--hot", "--hot-update",
        action="store_true",
        dest="hot_update",
        help="热更模式：仅登录服务器拉取 git 代码更新，更新成功即结束（不停服务、不装依赖、不重启）",
    )
    parser.add_argument(
        "--fe",
        action="store_true",
        dest="restart_fe",
        help="配合 --hot 使用：拉取 git 代码后，重启前端服务（不停后端、不装依赖）",
    )
    parser.add_argument(
        "--rd",
        action="store_true",
        dest="restart_rd",
        help="配合 --hot 使用：拉取 git 代码后，重启后端服务（不停前端、不装依赖）",
    )
    parser.add_argument(
        "--restart-fe",
        action="store_true",
        dest="restart_frontend",
        help="（已废弃，等价于 --hot --fe）仅重启前端：拉取 git 代码后，重启前端服务",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 兼容旧参数 --restart-fe：等价于 --hot --fe
    if args.restart_frontend:
        args.hot_update = True
        args.restart_fe = True

    # 指定了 --fe / --rd 时自动视为热更模式（可省略 --hot）
    if args.restart_fe or args.restart_rd:
        args.hot_update = True

    # 决定本次执行动作
    if not args.hot_update:
        action = "deploy"
    elif args.restart_fe and args.restart_rd:
        action = "restart_both"
    elif args.restart_fe:
        action = "restart_fe"
    elif args.restart_rd:
        action = "restart_rd"
    else:
        action = "hot"

    action_desc_map = {
        "deploy": "一键部署",
        "hot": "热更（仅更新代码）",
        "restart_fe": "热更 + 重启前端",
        "restart_rd": "热更 + 重启后端",
        "restart_both": "热更 + 重启前后端",
    }

    log("=" * 40, "INFO")
    log(f"git {action_desc_map[action]}启动", "STEP")
    log("=" * 40, "INFO")

    script_dir = os.path.dirname(os.path.abspath(__file__))

    log(f"脚本目录: {script_dir}", "INFO")

    config = load_config(script_dir)
    if not validate_config(config):
        sys.exit(1)

    ssh = None
    deploy_success = False
    try:
        ssh = connect_server(config)
        if action == "hot":
            deploy_success = hot_update_on_server(ssh, config)
        elif action == "restart_fe":
            deploy_success = restart_frontend_on_server(ssh, config)
        elif action == "restart_rd":
            deploy_success = restart_backend_on_server(ssh, config)
        elif action == "restart_both":
            deploy_success = restart_both_on_server(ssh, config)
        else:
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

    if deploy_success:
        log("=" * 40, "INFO")
        log("全部完成", "OK")
        log("=" * 40, "INFO")
    else:
        log("=" * 40, "INFO")
        log(f"{action_desc_map[action]}未完成，存在错误", "ERROR")
        log("=" * 40, "INFO")
        sys.exit(1)


if __name__ == "__main__":
    main()
