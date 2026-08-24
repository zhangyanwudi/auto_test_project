#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socket
import subprocess

# 常见虚拟网卡前缀，检测本机 IP 时跳过，避免拿到 docker/veth 等地址
_VIRTUAL_IF_PREFIXES = ('docker', 'veth', 'br-', 'virbr', 'tun', 'tap', 'vnet', 'lo')


def _is_valid_ipv4(ip):
    """校验是否为可对外访问的 IPv4 地址（排除回环、链路本地）。"""
    if not ip:
        return False
    if ip.startswith('127.'):
        return False
    if ip.startswith('169.254.'):  # 链路本地地址，无法用于对外访问
        return False
    try:
        parts = ip.split('.')
        return len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)
    except (ValueError, AttributeError):
        return False


def get_local_ip():
    """
    获取本机局域网 IPv4 地址（非 loopback、非链路本地）。

    依次尝试多种方式，保证在内网 / 无外网的测试服务器上也能「以机器 IP 为准」：
      1. UDP 出网路由探测：让系统选出默认路由对应的源 IP（能出网时最准，不会真正发包）
      2. 系统命令兜底：ip -4 addr（Linux）、hostname -I（Linux）、ipconfig（macOS）
      3. hostname 解析兜底

    返回:
        str | None: 本机 IP；检测失败返回 None
    """
    # 1) UDP 出网路由探测（借用系统路由选路，不真正发送数据）
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1)
            sock.connect(('8.8.8.8', 80))
            ip = sock.getsockname()[0]
            if _is_valid_ipv4(ip):
                return ip
    except OSError:
        pass

    # 2) 系统命令兜底（无外网环境）
    #    2.1 Linux：ip -4 addr，按行过滤虚拟网卡
    try:
        out = subprocess.run(
            ['ip', '-4', '-o', 'addr', 'show', 'scope', 'global'],
            capture_output=True, text=True, timeout=2,
        ).stdout
        for line in out.splitlines():
            # 形如: 2: eth0    inet 10.0.0.5/24 brd 10.0.0.255 scope global eth0
            tokens = line.split()
            if len(tokens) < 4:
                continue
            iface = tokens[1].rstrip(':')
            if iface.startswith(_VIRTUAL_IF_PREFIXES):
                continue
            for token in tokens:
                ip = token.split('/')[0]  # 去掉 CIDR 前缀
                if _is_valid_ipv4(ip):
                    return ip
    except Exception:
        pass

    #    2.2 Linux：hostname -I（纯 IP 列表）
    try:
        out = subprocess.run(
            ['hostname', '-I'], capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        for token in out.split():
            ip = token.split('/')[0]
            if _is_valid_ipv4(ip):
                return ip
    except Exception:
        pass

    #    2.3 macOS：ipconfig getifaddr
    for iface in ('en0', 'en1'):
        try:
            out = subprocess.run(
                ['ipconfig', 'getifaddr', iface],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip()
            ip = out.split()[0] if out else ''
            if _is_valid_ipv4(ip):
                return ip
        except Exception:
            pass

    # 3) hostname 解析兜底
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _is_valid_ipv4(ip):
                return ip
    except OSError:
        pass

    return None
