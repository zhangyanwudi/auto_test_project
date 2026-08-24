#!/usr/bin/env python3
"""
GP 商业化日志 - adb logcat 本地代理
=====================================
持久运行，通过轮询服务器获取启停指令，无需手动启停 adb。

用法:
    python gp_logcat_agent.py --server http://192.168.1.100:8000 --token <admin_token>

启动后保持运行，页面点击「启动」→ 代理自动执行 adb logcat
页面点击「停止」→ 代理终止 adb，回到待命状态
Ctrl+C 退出。
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error


# ---------------------------------------------------------------------------
# 命令行参数
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description='GP 商业化日志 - adb logcat 本地代理（持久模式）',
    )
    parser.add_argument(
        '--server', '-s',
        default=os.environ.get('GP_LOGCAT_SERVER', ''),
        help='服务器地址，如 http://192.168.1.100:8000',
    )
    parser.add_argument(
        '--token', '-t',
        default=os.environ.get('GP_LOGCAT_TOKEN', ''),
        help='登录 token',
    )
    parser.add_argument(
        '--adb-path',
        default='adb',
        help='adb 路径（默认从 PATH 查找）',
    )
    parser.add_argument(
        '--poll-interval',
        type=float,
        default=1.0,
        help='轮询指令的间隔秒数（默认 1 秒）',
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def api_post(url, token, data):
    """发送 POST 请求，返回 (ok, response_dict)。"""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    try:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            return True, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return False, {'code': e.code, 'message': body[:200]}
    except Exception as e:
        return False, {'code': 0, 'message': str(e)}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    server = args.server.rstrip('/')
    token = args.token

    if not server or not token:
        print('[错误] 请指定 --server 和 --token（或设置环境变量 GP_LOGCAT_SERVER / GP_LOGCAT_TOKEN）')
        sys.exit(1)

    ingest_url = f'{server}/api/gp_logcat/ingest/'

    print(f'[代理] 服务器: {server}')
    print(f'[代理] 已连接，等待页面指令...')
    print(f'[代理] 在页面点击「启动日志」开始抓取，点击「停止」终止')
    print(f'[代理] 按 Ctrl+C 退出')
    print('-' * 50)

    # 检查 adb
    adb_cmd = [args.adb_path, 'logcat']
    try:
        subprocess.run([args.adb_path, 'version'], capture_output=True, timeout=5)
    except Exception:
        print('[错误] 找不到 adb，请确认 Android SDK Platform-Tools 已安装')
        sys.exit(1)

    proc = None          # adb 子进程
    filter_str = ''      # 当前过滤条件
    shutdown = False

    def on_signal(sig, frame):
        nonlocal shutdown
        print('\n[代理] 正在退出...')
        shutdown = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    def stop_adb():
        nonlocal proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        proc = None

    def start_adb(filt):
        nonlocal proc, filter_str
        stop_adb()
        filter_str = filt
        cmd = [args.adb_path, 'logcat']
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            print(f'[错误] 启动 adb logcat 失败: {e}')
            return False
        print(f'[代理] adb logcat 已启动（过滤: {filter_str or "无"}）')
        return True

    try:
        while not shutdown:
            # 收集 adb 输出
            lines_batch = []
            if proc and proc.poll() is None:
                # 非阻塞读取 adb stdout
                import select
                while True:
                    if sys.platform == 'win32':
                        import msvcrt
                        # Windows 不支持 select，简化处理
                        line = proc.stdout.readline()
                        if line:
                            stripped = line.rstrip('\n\r')
                            if stripped:
                                lines_batch.append(stripped)
                        else:
                            # adb 进程退出
                            print('[代理] adb logcat 进程已退出')
                            proc = None
                            break
                        if len(lines_batch) >= 50:
                            break
                    else:
                        ready, _, _ = select.select([proc.stdout], [], [], 0.05)
                        if ready:
                            line = proc.stdout.readline()
                            if line:
                                stripped = line.rstrip('\n\r')
                                if stripped:
                                    lines_batch.append(stripped)
                            else:
                                print('[代理] adb logcat 进程已退出')
                                proc = None
                                break
                        else:
                            break

            # 发送日志或心跳
            if lines_batch:
                ok, resp = api_post(ingest_url, token, {'lines': lines_batch})
            else:
                ok, resp = api_post(ingest_url, token, {'heartbeat': True})

            # 处理服务器返回的控制指令
            if ok and resp.get('code') == 0:
                ctrl = resp.get('data', {}).get('agent_control', {})
                action = ctrl.get('action', 'none')
                if action == 'start':
                    f = ctrl.get('filter', '')
                    print(f'[代理] 收到启动指令（过滤: {f or "无"}）')
                    start_adb(f)
                elif action == 'stop':
                    if proc and proc.poll() is None:
                        print('[代理] 收到停止指令')
                        stop_adb()
            elif not ok:
                err_msg = resp.get('message', '未知错误')
                # 不 flood 错误消息，只在状态变化时提示
                if not hasattr(main, '_last_error') or main._last_error != err_msg:
                    print(f'[警告] 服务器通信异常: {err_msg}')
                    main._last_error = err_msg

            # 等待轮询间隔
            time.sleep(args.poll_interval)

    finally:
        stop_adb()
        print('[代理] 已退出')


if __name__ == '__main__':
    main()
