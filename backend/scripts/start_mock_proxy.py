#!/usr/bin/env python3
"""
Mock API 代理 — 命令行独立启动脚本
====================================
从数据库 z_mock_api_rule 表中读取启用状态（status=1）的规则，
启动 mitmproxy 代理服务，拦截匹配的请求并返回 mock 数据。

用法:
    # 测试服推荐：前台常驻 + 数据库规则自动轮询（页面启停规则约 2s 内生效）
    python scripts/start_mock_proxy.py --port 8080 --reload-interval 2

    # 后台运行
    python scripts/start_mock_proxy.py --port 8080 --background

    # 同时加载 JSON 配置文件中的静态规则
    python scripts/start_mock_proxy.py -c mock_config.json

    # 启用配置文件热加载（文件变更自动重载）
    python scripts/start_mock_proxy.py -c mock_config.json --watch

    # 查看帮助
    python scripts/start_mock_proxy.py --help

依赖:
    pip install mitmproxy
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path


# ============================================================
# Django 环境引导
# ============================================================

def _setup_django():
    """
    初始化 Django 环境，使脚本可以独立访问 ORM。
    返回 (ok: bool, error_msg: str)
    """
    script_dir = Path(__file__).resolve().parent
    backend_dir = script_dir.parent  # 脚本位于 backend/scripts/ 下
    sys.path.insert(0, str(backend_dir))

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

    try:
        import django
        django.setup()
        return True, ''
    except Exception as e:
        return False, f'Django 环境初始化失败: {e}\n请确认当前工作目录为项目根目录，或设置 DJANGO_SETTINGS_MODULE 环境变量'


def get_local_ip():
    """
    获取本机主网卡 IPv4 地址（非回环），用于日志展示与手机代理配置。

    复用 base_utils.network_utils 的多级检测（UDP 路由探测 → 系统命令 → hostname 解析），
    在无外网的测试服务器上也能正确返回「机器 IP」，而不是退回 127.0.0.1。
    检测失败时兜底返回 '127.0.0.1'。
    """
    try:
        from base_utils.network_utils import get_local_ip as _detect_local_ip
        return _detect_local_ip() or '127.0.0.1'
    except Exception:
        # 兜底：import 失败（如 sys.path 未就绪）时退回 UDP 探测逻辑
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            try:
                s.connect(('8.8.8.8', 80))
                return s.getsockname()[0]
            except (socket.error, OSError):
                return '127.0.0.1'
            finally:
                s.close()
        except Exception:
            return '127.0.0.1'


def _load_rules_from_db(server, quiet=False):
    """从数据库加载启用状态的 Mock 规则到代理实例。返回加载条数。"""
    from apps.mock_api.models import ZMockApiRule

    qs = ZMockApiRule.objects.filter(status=1).order_by('sort_order', 'id')
    count = server.load_rules_from_db(qs)

    if quiet:
        return count

    # 打印已加载的规则概览
    if count > 0:
        print(f'\n{"=":>60}')
        print(f'  已从数据库加载 {count} 条启用规则:')
        print(f'{"=":>60}')
        for i, rule in enumerate(qs, 1):
            resp_preview = ''
            if rule.response_data:
                try:
                    preview = rule.response_data[:80]
                    resp_preview = f' → {preview}...' if len(rule.response_data) > 80 else f' → {preview}'
                except Exception:
                    pass
            elif rule.response_file:
                resp_preview = f' → 📄 {rule.response_file}'
            print(f'  {i:>2}. [{rule.match_type}] {rule.url_pattern}{resp_preview}')
        print(f'{"=":>60}\n')
    else:
        print('\n⚠️  警告: 数据库中没有启用状态的规则，代理将以空规则集启动。')
        print('   请通过 Web 页面「Mock接口管理」创建并启用规则。\n')

    return count


def _start_db_reload_watcher(server, interval, stop_event):
    """后台轮询数据库启用规则，页面启停规则后可自动同步到本进程。"""
    import threading
    from apps.mock_api.models import ZMockApiRule

    def _fingerprint():
        rows = ZMockApiRule.objects.filter(status=1).order_by('sort_order', 'id').values_list(
            'id', 'update_time', 'status', 'url_pattern', 'response_data', 'status_code', 'match_type'
        )
        return tuple((
            r[0],
            r[1].isoformat() if r[1] else '',
            r[2],
            r[3],
            r[4] or '',
            r[5],
            r[6],
        ) for r in rows)

    last_fp = _fingerprint()

    def _loop():
        nonlocal last_fp
        while not stop_event.wait(timeout=max(0.5, float(interval))):
            try:
                fp = _fingerprint()
                if fp != last_fp:
                    count = _load_rules_from_db(server, quiet=True)
                    last_fp = fp
                    print(f'🔄 检测到数据库规则变更，已同步 {count} 条启用规则到代理')
            except Exception as e:
                print(f'⚠️  数据库规则轮询失败: {e}')

    t = threading.Thread(target=_loop, name='mock-db-reloader', daemon=True)
    t.start()
    return t


# ============================================================
# 命令行参数
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='Mock API 代理 — 从数据库加载规则并启动 mitmproxy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/start_mock_proxy.py
  python scripts/start_mock_proxy.py --port 18080
  python scripts/start_mock_proxy.py --reload-interval 2
  python scripts/start_mock_proxy.py -c mock_config.json --watch
        """,
    )
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=8080,
        help='代理监听端口（默认: 8080）',
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='代理监听地址。默认: 0.0.0.0（所有接口）。'
             '可选: 127.0.0.1（仅本地）、auto（自动检测本机IP）、或指定IP',
    )
    parser.add_argument(
        '-c', '--config',
        type=str,
        default=None,
        help='额外的 JSON 配置文件路径（补充静态规则）',
    )
    parser.add_argument(
        '-w', '--watch',
        action='store_true',
        help='启用配置文件热加载（仅当指定了 -c 时有效）',
    )
    parser.add_argument(
        '--background',
        action='store_true',
        help='后台运行（默认前台阻塞，Ctrl+C 退出）',
    )
    parser.add_argument(
        '--no-db',
        action='store_true',
        help='不从数据库加载规则（仅使用 -c 配置文件）',
    )
    parser.add_argument(
        '--reload-interval',
        type=float,
        default=2.0,
        help='轮询数据库规则变更的间隔秒数（默认 2；设为 0 关闭轮询）',
    )
    return parser.parse_args()


# ============================================================
# 主入口
# ============================================================

def main():
    args = parse_args()

    # 1. 初始化 Django
    ok, err = _setup_django()
    if not ok:
        print(err, file=sys.stderr)
        sys.exit(1)

    from base_utils.mock_api_utils import MockApiServer, logger
    import threading

    # 2. 创建代理实例
    # --host auto 时自动检测本机 IP
    bind_host = args.host if args.host != 'auto' else get_local_ip()
    config_dict = {}
    if args.config:
        config_dict['config_file'] = str(Path(args.config).resolve())

    server = MockApiServer(
        config=config_dict if config_dict else None,
        port=args.port,
        host=bind_host,
    )

    # 设置全局实例（同进程内可用；与 Django Web 进程相互独立）
    import base_utils.mock_api_utils as mu
    mu._server_instance = server

    # 3. 从数据库加载规则
    if not args.no_db:
        _load_rules_from_db(server)
    else:
        print('⚠️  --no-db 模式，跳过数据库规则加载')

    # 4. 如果指定了配置文件，加载静态规则（增量追加，不清空 DB 规则）
    if args.config:
        server.load_config_file(args.config)
        if args.watch:
            server.enable_hot_reload()

    # 5. 信号处理：Ctrl+C 优雅退出
    _stop_event = threading.Event()
    stop_requested = False
    try:
        def _on_signal(signum, frame):
            nonlocal stop_requested
            stop_requested = True
            print('\n⏸  收到中断信号，正在停止代理...')
            server.stop()
            _stop_event.set()

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)
    except Exception:
        pass  # 非主线程可能无法设置信号，忽略

    # 5.1 数据库规则轮询（Web 页面启停规则后自动同步）
    if not args.no_db and args.reload_interval and args.reload_interval > 0:
        _start_db_reload_watcher(server, args.reload_interval, _stop_event)
        print(f'📡 数据库规则轮询已启用 (interval={args.reload_interval}s)')

    # 6. 启动代理
    local_ip = get_local_ip()

    print(f'\n🚀 Mock API 代理启动中...')
    print(f'   监听地址: {bind_host}:{args.port}', end='')
    if bind_host == '0.0.0.0':
        print(' (所有网络接口)')
    elif bind_host == '127.0.0.1':
        print(' (仅本地)')
    else:
        print()
    print(f'   本地访问: http://127.0.0.1:{args.port}')
    if local_ip and local_ip != '127.0.0.1':
        print(f'   网络访问: http://{local_ip}:{args.port}')
        print()
        print(f'   📱 手机端配置（以本机 IP 为准）:')
        print(f'      Wi-Fi 代理 -> 手动')
        print(f'      服务器: {local_ip}')
        print(f'      端口:   {args.port}')
        print(f'   证书下载: 手机浏览器访问 http://mitm.it 即可下载并安装证书')
        print(f'   ⚠️  若手机无法打开 mitm.it，请先确认手机能访问 {local_ip}:{args.port}')
        print(f'      （服务器需放通 {args.port} 端口，且手机与该 IP 网络互通）')
    print(f'   数据库规则: {"已加载" if not args.no_db else "已跳过"}')
    print(f'   配置文件: {args.config or "无"}')
    if args.watch:
        print(f'   热加载: 已启用')
    if args.background:
        print(f'   运行模式: 后台')
    print()

    if args.background:
        ok = server.start(blocking=False)
        if not ok:
            print('❌ 代理启动失败', file=sys.stderr)
            sys.exit(1)
        print(f'✅ 代理已在后台启动 (port={args.port})')
        print(f'   按 Ctrl+C 停止...')
        try:
            while server.is_running() and not _stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            print('\n⏸  正在停止...')
            server.stop()
            _stop_event.set()
    else:
        # 前台模式也走非阻塞 + 等待，以便信号处理和 DB 轮询共存
        ok = server.start(blocking=False)
        if not ok:
            print('❌ 代理启动失败', file=sys.stderr)
            sys.exit(1)
        print(f'✅ 代理已启动 (port={args.port})，按 Ctrl+C 停止...')
        try:
            while server.is_running() and not _stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            print('\n⏸  正在停止...')
            server.stop()
            _stop_event.set()

    print('✅ 代理已停止')


if __name__ == '__main__':
    main()
