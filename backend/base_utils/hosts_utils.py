#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, subprocess, tempfile,re

# ===== 需要增加的记录 =====
# 格式：IP   域名
HOSTS_LINES = """
192.168.50.249 datatester-test.afafb.com
"""
# ==========================

def run_as_root():
    """若当前无 root 权限，则通过 osascript 重新以 sudo 启动自身"""
    if os.geteuid() != 0:
        cmd = ['osascript', '-e',
               f'do shell script "{sys.executable} {os.path.realpath(__file__)}" with administrator privileges']
        subprocess.run(cmd)
        sys.exit()

def add_hosts():
    run_as_root()
    hosts_path = "/etc/hosts"
    with open(hosts_path, "r", encoding="utf-8") as f:
        content = f.read()

    need_add = []
    for line in HOSTS_LINES.splitlines():
        if line.strip() and line.strip() not in content:
            need_add.append(line.strip())

    if not need_add:
        subprocess.run(["osascript", "-e", 'display notification "hosts 已包含所需记录，无需重复添加" with title "Hosts"'])
        return

    new_content = content.rstrip() + "\n" + "\n".join(need_add) + "\n"
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as tmp:
        tmp.write(new_content)
        tmp.flush()
        subprocess.run(["sudo", "cp", tmp.name, hosts_path])
    subprocess.run(["osascript", "-e", 'display notification "hosts 写入完成" with title "Hosts"'])


def clear_hosts():
    run_as_root()
    hosts_path = "/etc/hosts"
    with open(hosts_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 保留系统默认行（含 localhost / broadcasthost / ::1 等）
    kept = [l for l in lines if re.search(r"^(#|$)|127\.0\.0\.1|::1|localhost|broadcasthost", l, flags=re.I)]
    new_content = "".join(kept)
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as tmp:
        tmp.write(new_content)
        tmp.flush()
        subprocess.run(["sudo", "cp", tmp.name, hosts_path])
    subprocess.run(["osascript", "-e", 'display notification "hosts 已清理完成" with title "Hosts"'])


def show_hosts():
    hosts_path = "/etc/hosts"
    with open(hosts_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 只保留非空、非注释行
    effective = [l.rstrip() for l in lines if l.strip() and not l.strip().startswith("#")]

    if not effective:
        msg = "当前 hosts 里没有生效的自定义映射。"
    else:
        msg = "当前生效的 hosts 记录：\n" + "\n".join(effective)

    # ① 终端打印（双击时能看到）
    print(msg)
    # ② 再弹一个 macOS 通知窗口
    subprocess.run([
        "osascript", "-e",
        f'display notification "{msg.replace(chr(10), chr(10))}" with title "当前Hosts"'
    ])


if __name__ == "__main__":
    # add_hosts()
    clear_hosts()
    show_hosts()