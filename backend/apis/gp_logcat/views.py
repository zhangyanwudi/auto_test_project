"""
GP 商业化日志 - 实时 adb logcat 查看
======================================
- LogBuffer：线程安全日志缓冲区，支持 SSE 长连接阻塞读取
- ingest：接收本地代理脚本推送的日志行
- stream：SSE 实时日志流，供前端 EventSource 消费
- status：查询缓冲区状态
- clear：清空缓冲区
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque

from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.users.models import ZUser


# ---------------------------------------------------------------------------
# 日志缓冲区（模块级单例）
# ---------------------------------------------------------------------------

class LogBuffer:
    """线程安全的日志缓冲区。

    使用 queue.Queue 实现阻塞读取，供 SSE 长连接等待新日志；
    同时用 deque 保留最近 N 条历史日志，供新连接回看。
    """

    def __init__(self, max_history=5000):
        self._queue = queue.Queue()
        self._history = deque(maxlen=max_history)
        self._lock = threading.Lock()
        self._last_activity = None  # datetime，记录最后 ingest 时间

    def append(self, line: str):
        """写入一条日志。"""
        now = time.time()
        with self._lock:
            self._history.append(line)
            self._last_activity = now
        self._queue.put(line)

    def append_batch(self, lines):
        """批量写入日志。"""
        now = time.time()
        with self._lock:
            for line in lines:
                self._history.append(line)
                self._queue.put(line)
            self._last_activity = now

    def get_recent(self, count=200):
        """获取最近 N 条历史日志。"""
        with self._lock:
            items = list(self._history)[-count:]
        return items

    def clear(self):
        """清空历史日志和队列。"""
        with self._lock:
            self._history.clear()
            self._last_activity = None
        self._drain_queue()

    def _drain_queue(self):
        """排空队列中所有积压条目。"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def get_total_count(self):
        """获取当前历史日志数。"""
        with self._lock:
            return len(self._history)

    def get_last_activity(self):
        """获取最后一条日志的写入时间（Unix timestamp），无记录则返回 None。"""
        with self._lock:
            return self._last_activity

    def listen(self, timeout=25):
        """生成器：阻塞等待新日志。

        每收到一条日志就 yield；超时 yield None 作为心跳标记。
        调用方检测到 None 时应发送 SSE 注释保持连接。
        """
        try:
            while True:
                try:
                    line = self._queue.get(timeout=timeout)
                    yield line
                except queue.Empty:
                    yield None  # 心跳
        except GeneratorExit:
            pass


# 全局单例
_log_buffer = LogBuffer()


# ---------------------------------------------------------------------------
# adb 子进程管理器（模块级单例）
# ---------------------------------------------------------------------------

class AdbManager:
    """管理 adb logcat 子进程的生命周期。

    支持：
    - 启动 adb logcat 子进程，stdout 实时写入 LogBuffer
    - 停止子进程
    - 查询运行状态
    - 检查 adb 是否可用
    """

    def __init__(self):
        self._proc = None           # subprocess.Popen
        self._reader_thread = None  # stdout 读取线程
        self._lock = threading.Lock()
        self._started_at = None     # 启动时间
        self._filter = ''           # 当前过滤参数字符串
        self._keywords = []         # 过滤关键字列表（小写）

    def is_running(self):
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def get_filter(self):
        with self._lock:
            return self._filter

    def get_started_at(self):
        with self._lock:
            return self._started_at

    @staticmethod
    def check_adb():
        """检查 adb 是否可用。返回 (ok: bool, path: str, message: str)。"""
        adb_path = shutil.which('adb')
        if not adb_path:
            return False, '', '未检测到 adb 命令。请安装 Android SDK Platform-Tools 并添加到 PATH'
        return True, adb_path, 'adb 可用'

    def start(self, filter_str=''):
        """启动 adb logcat 子进程。

        Args:
            filter_str: 内容过滤关键字，空格分隔多个关键字（AND 逻辑）。
                        例如 "klog" → 匹配含 "klog" 的行；
                        "klog ads" → 同时含 "klog" 和 "ads" 的行；
                        空字符串 → 不过滤，输出全部日志。

        Returns:
            (ok: bool, message: str)
        """
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return False, 'adb logcat 已在运行中'

            # 检查 adb 可用性
            ok, adb_path, msg = self.check_adb()
            if not ok:
                return False, msg

            # 解析过滤关键字（Python 侧做内容过滤，大小写不敏感）
            keywords = []
            if filter_str and filter_str.strip():
                for k in filter_str.strip().split():
                    k = k.strip()
                    if not k:
                        continue
                    # 自动剥离 :* :V :D :I :W :E :F 等级别后缀（兼容旧格式 tag:level）
                    if ':' in k:
                        k = k.split(':')[0]
                    if k:
                        keywords.append(k.lower())
            self._keywords = keywords
            self._filter = filter_str.strip() if keywords else ''

            # 构建命令（始终输出全部日志，过滤在 Python 层做）
            cmd = [adb_path, 'logcat']

            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                self._started_at = time.time()
            except Exception as e:
                self._proc = None
                self._started_at = None
                self._keywords = []
                self._filter = ''
                return False, f'启动 adb logcat 失败: {e}'

            # 启动后台读取线程
            self._stop_reader = threading.Event()
            self._reader_thread = threading.Thread(
                target=self._read_stdout,
                daemon=True,
            )
            self._reader_thread.start()

            return True, f'adb logcat 已启动（过滤: {self._filter or "无"}）'

    def stop(self):
        """停止 adb logcat 子进程。

        Returns:
            (ok: bool, message: str)
        """
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = None
                self._reader_thread = None
                self._started_at = None
                self._filter = ''
                return True, 'adb logcat 已停止'

            # 通知读取线程停止
            if self._stop_reader:
                self._stop_reader.set()

            # 终止子进程
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=3)
            except Exception as e:
                pass  # 进程可能已经退出

            self._proc = None
            self._reader_thread = None
            self._started_at = None
            self._filter = ''

            # 排空队列中 adb 进程残余的输出，避免 SSE 继续推送
            _log_buffer._drain_queue()

            return True, 'adb logcat 已停止'

    def _read_stdout(self):
        """后台线程：读取 adb stdout，按关键字过滤后写入 LogBuffer。"""
        try:
            while not self._stop_reader.is_set():
                line = self._proc.stdout.readline()
                if line:
                    stripped = line.rstrip('\n\r')
                    if stripped:
                        # Python 层内容过滤（大小写不敏感 AND 逻辑）
                        if self._match_keywords(stripped):
                            _log_buffer.append(stripped)
                elif self._proc.poll() is not None:
                    break
        except Exception:
            pass
        finally:
            # 进程退出时自动清理状态
            with self._lock:
                self._proc = None
                self._reader_thread = None
                self._started_at = None
                self._keywords = []
                self._filter = ''

    def _match_keywords(self, line):
        """检查日志行是否匹配所有过滤关键字。

        优先匹配 logcat TAG 字段（格式：... Level  TAG: message），
        无法解析格式时回退到全行子串匹配。
        大小写不敏感，AND 逻辑。
        """
        if not self._keywords:
            return True

        # 尝试按标准 logcat 格式提取 TAG
        # 格式: MM-DD HH:MM:SS.mmm PID TID LEVEL  TAG: message
        m = re.match(
            r'^\S+\s+\S+\s+\S+\s+\S+\s+[VDIWEF]\s+(\S+):',
            line,
        )
        if m:
            tag = m.group(1).lower()
            return all(kw in tag for kw in self._keywords)

        # 非标准格式（如 adb 自身输出），回退到全行匹配
        lower_line = line.lower()
        return all(kw in lower_line for kw in self._keywords)


# 全局单例
_adb_manager = AdbManager()


class ServerAgentManager:
    """服务器模式下管理本地代理子进程的生命周期。

    服务器模式下不走 AdbManager（不直接跑 adb），
    而是在服务器上启动 gp_logcat_agent.py 作为子进程，
    由代理通过 ingest 端点回推日志。
    """

    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._started_at = None

    @property
    def script_path(self):
        return os.path.join(settings.BASE_DIR, 'scripts', 'gp_logcat_agent.py')

    def is_running(self):
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def check_script(self):
        """检查代理脚本是否存在。返回 (ok, message)。"""
        if os.path.exists(self.script_path):
            return True, '代理脚本就绪'
        return False, f'代理脚本不存在: {self.script_path}'

    def start(self, server_url, token, filter_str=''):
        """在服务器上启动代理子进程。

        Args:
            server_url: 服务器地址（代理连接用，通常 http://127.0.0.1:8000）
            token: 用户认证 token
            filter_str: TAG 过滤条件
        """
        with self._lock:
            # 停止旧的
            self._kill_existing()

            # 检查脚本
            ok, msg = self.check_script()
            if not ok:
                return False, msg

            # 先设置启动指令（代理启动后轮询即可获取）
            _agent_control['action'] = 'start'
            _agent_control['filter'] = filter_str
            _agent_control['requested_at'] = time.time()

            # 构建命令
            cmd = [
                sys.executable, self.script_path,
                '--server', server_url,
                '--token', token,
            ]
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                self._started_at = time.time()
            except Exception as e:
                self._proc = None
                self._started_at = None
                return False, f'启动代理子进程失败: {e}'

            # 后台读取代理 stdout（只记日志，不阻塞）
            t = threading.Thread(target=self._read_output, daemon=True)
            t.start()

            return True, '服务器代理已启动'

    def stop(self):
        """停止代理子进程。"""
        with self._lock:
            _agent_control['action'] = 'stop'
            _agent_control['requested_at'] = time.time()
            time.sleep(0.3)  # 给代理一点时间响应停止指令
            self._kill_existing()
            return True, '服务器代理已停止'

    def _kill_existing(self):
        if self._proc is None:
            return
        if self._proc.poll() is None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=2)
            except Exception:
                pass
        self._proc = None
        self._started_at = None

    def _read_output(self):
        """读取代理 stdout 输出到 Django 日志。"""
        try:
            import logging
            logger = logging.getLogger('apis.gp_logcat.agent')
            while self._proc and self._proc.poll() is None:
                line = self._proc.stdout.readline()
                if line:
                    logger.debug(line.rstrip())
                else:
                    break
        except Exception:
            pass


# 全局单例
_server_agent = ServerAgentManager()

# 代理模式控制状态（页面按钮 → 服务端 → 代理轮询获取）
_agent_control = {
    'action': 'none',    # 'start' | 'stop' | 'none'
    'filter': '',        # 过滤关键字
    'requested_at': 0,   # 请求时间戳
}

# 本地代理最近一次心跳时间（含纯 heartbeat / 推送日志）
_agent_last_seen = 0.0
# 心跳超时判定（秒）：超过则认为代理离线
_AGENT_ONLINE_TTL = 5.0


# ---------------------------------------------------------------------------
# Token 校验工具
# ---------------------------------------------------------------------------

def _extract_token(request):
    """从请求中提取 token 字符串（不校验有效性）。"""
    auth = request.META.get('HTTP_AUTHORIZATION') or ''
    if auth.startswith('Bearer '):
        return auth[7:].strip()
    token = request.GET.get('token', '').strip()
    return token or ''


def _get_valid_user(request):
    """从请求中提取并校验 token，返回 ZUser 或 None。"""
    token = _extract_token(request)
    if token:
        return ZUser.get_valid_user_by_token(token)
    return None


def _unauthorized():
    """返回 401 JSON 响应。"""
    return JsonResponse(
        {'code': 401, 'success': False, 'message': '未授权或 token 无效', 'data': None},
        status=401,
    )


def _ok(data=None, msg='成功'):
    return JsonResponse({
        'code': 0, 'success': True, 'message': msg, 'data': data or {},
    })


def _fail(msg, code=400, status=400):
    return JsonResponse({
        'code': code, 'success': False, 'message': msg, 'data': None,
    }, status=status)


# ---------------------------------------------------------------------------
# API 视图
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(['POST'])
def gp_logcat_ingest(request):
    """日志接入 / 代理心跳接口。

    接收 JSON body:
        {"lines": ["line1", ...]}       — 批量日志
        {"line": "single log line"}      — 单条日志
        {"heartbeat": true}              — 心跳（代理轮询控制指令）

    响应中附带 agent_control，代理根据 action 执行启停。
    需要有效 token。
    """
    user = _get_valid_user(request)
    if not user:
        return _unauthorized()

    try:
        body = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    # 处理日志数据
    global _agent_last_seen
    lines = body.get('lines')
    single = body.get('line')
    heartbeat = body.get('heartbeat', False)
    ingested = 0

    if lines and isinstance(lines, list):
        valid_lines = [str(l) for l in lines if l and str(l).strip()]
        if valid_lines:
            _log_buffer.append_batch(valid_lines)
            ingested = len(valid_lines)
    elif single and isinstance(single, str) and single.strip():
        _log_buffer.append(single.strip())
        ingested = 1

    # 任意 ingest（含纯心跳）均刷新代理在线时间
    if ingested or heartbeat:
        _agent_last_seen = time.time()

    # 构建响应：附带代理控制指令
    ctrl = _agent_control.copy()
    # 指令已读取，重置为 none
    if ctrl['action'] != 'none':
        _agent_control['action'] = 'none'
        _agent_control['filter'] = ''

    return _ok({
        'ingested': ingested,
        'agent_control': ctrl,
    })


@require_http_methods(['GET'])
def gp_logcat_stream(request):
    """SSE 实时日志流。

    先发送最近 200 条历史日志，然后持续推送新日志。
    每 25 秒无数据时发送心跳注释保持连接。

    认证方式：URL 查询参数 ?token=<token>（EventSource 不支持自定义 header）。
    """
    user = _get_valid_user(request)
    if not user:
        return _unauthorized()

    def event_stream():
        # 1) 先发送历史日志
        recent = _log_buffer.get_recent(200)
        for line in recent:
            yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"

        # 2) 持续推送新日志
        for line in _log_buffer.listen(timeout=25):
            if line is None:
                # SSE 注释行：心跳
                yield ": heartbeat\n\n"
            else:
                yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # 禁用 nginx 缓冲
    return response


@require_http_methods(['GET'])
def gp_logcat_status(request):
    """查询日志缓冲区状态及 adb 子进程状态。

    返回：日志数、adb 运行状态、最后活跃时间等。
    """
    user = _get_valid_user(request)
    if not user:
        return _unauthorized()

    last_act = _log_buffer.get_last_activity()
    adb_running = _adb_manager.is_running()
    adb_started = _adb_manager.get_started_at()

    # 检查环境
    adb_ok, adb_path, adb_msg = AdbManager.check_adb()
    agent_running = _server_agent.is_running()
    agent_script_ok, _ = _server_agent.check_script()

    # 本地代理在线：最近心跳在 TTL 内
    agent_online = bool(
        _agent_last_seen and (time.time() - _agent_last_seen) <= _AGENT_ONLINE_TTL
    )

    return _ok({
        'total_count': _log_buffer.get_total_count(),
        'max_history': 5000,
        'last_activity': last_act,
        'last_activity_iso': time.strftime(
            '%Y-%m-%d %H:%M:%S',
            time.localtime(last_act),
        ) if last_act else None,
        'adb_running': adb_running or agent_running,
        'adb_started_at': adb_started,
        'adb_started_iso': time.strftime(
            '%Y-%m-%d %H:%M:%S',
            time.localtime(adb_started),
        ) if adb_started else None,
        'adb_filter': _adb_manager.get_filter() if adb_running else (_agent_control.get('filter', '') if agent_running else ''),
        'adb_available': adb_ok,
        'adb_path': adb_path,
        'adb_check_msg': adb_msg,
        'server_agent_running': agent_running,
        'server_agent_script_ok': agent_script_ok,
        'agent_online': agent_online,
        'agent_last_seen': _agent_last_seen or None,
    })


@csrf_exempt
@require_http_methods(['POST'])
def gp_logcat_start(request):
    """启动 adb logcat。

    接收 JSON body:
        {"mode": "server"|"local", "filter": "klog"}

    server 模式：服务器启动代理子进程，由代理管理 adb。
    local  模式：设置控制状态，由用户本地代理轮询获取并执行。
    """
    user = _get_valid_user(request)
    if not user:
        return _unauthorized()

    try:
        body = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}
    filter_str = body.get('filter', '').strip()
    mode = body.get('mode', 'server')

    if mode == 'local':
        # 本地代理模式：设置控制状态，等待轮询
        _agent_control['action'] = 'start'
        _agent_control['filter'] = filter_str
        _agent_control['requested_at'] = time.time()
        return _ok({
            'mode': 'local',
            'filter': filter_str,
            'message': '已发送启动指令，等待本地代理响应...',
        }, '已向本地代理发送启动指令')

    # 服务器模式：服务器启动代理子进程
    # 从请求中提取 token（传给代理子进程用）
    token = _extract_token(request)
    server_url = f'http://127.0.0.1:{request.get_port()}'

    ok, msg = _server_agent.start(server_url, token, filter_str)
    if not ok:
        # 如果代理脚本不存在，尝试用 AdbManager 直接跑 adb（兼容旧逻辑）
        adb_ok, adb_path, adb_msg = AdbManager.check_adb()
        if adb_ok:
            ok2, msg2 = _adb_manager.start(filter_str)
            if ok2:
                return _ok({
                    'mode': 'server_direct',
                    'adb_path': adb_path,
                }, '直接模式: ' + msg2)
        return _fail(msg, code=500, status=500)

    return _ok({
        'mode': 'server',
        'filter': filter_str,
    }, msg)


@csrf_exempt
@require_http_methods(['POST'])
def gp_logcat_stop(request):
    """停止 adb logcat。"""
    user = _get_valid_user(request)
    if not user:
        return _unauthorized()

    stopped = False

    # 服务器代理
    if _server_agent.is_running():
        ok, msg = _server_agent.stop()
        stopped = True

    # 服务器直连 adb
    if _adb_manager.is_running():
        ok, msg = _adb_manager.stop()
        stopped = True

    # 本地代理模式
    _agent_control['action'] = 'stop'
    _agent_control['filter'] = ''
    _agent_control['requested_at'] = time.time()

    if stopped:
        return _ok({'mode': 'server'}, '已停止')
    return _ok({
        'mode': 'local',
        'message': '已发送停止指令',
    }, '已发送停止指令')


@csrf_exempt
@require_http_methods(['POST'])
def gp_logcat_clear(request):
    """清空日志缓冲区。"""
    user = _get_valid_user(request)
    if not user:
        return _unauthorized()

    _log_buffer.clear()
    return _ok({}, '日志缓冲区已清空')


# ---------------------------------------------------------------------------
# 代理脚本下载
# ---------------------------------------------------------------------------

@require_http_methods(['GET'])
def gp_logcat_agent_script(request):
    """返回本地代理脚本内容（不需要认证，方便 curl 下载）。

    用法:
        curl -s http://server:8000/api/gp_logcat/agent/ | python3 - --server ... --token ... --filter ... --clear
    """
    script_path = os.path.join(settings.BASE_DIR, 'scripts', 'gp_logcat_agent.py')
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return HttpResponse('脚本文件不存在', status=404, content_type='text/plain')

    return HttpResponse(content, content_type='text/plain; charset=utf-8')


@require_http_methods(['GET'])
def gp_logcat_agent_bootstrap(request):
    """返回一键启动脚本：检测 Python → 按需下载代理 → 启动。

    查询参数:
        server: 服务器地址（可选，默认根据请求推断）
        token:  登录 token（必填）
        format: sh | command | bat（默认 sh；command 适合 macOS 双击）

    用法:
        curl -fsSL "http://server:8000/api/gp_logcat/agent/bootstrap/?token=xxx" | bash
    """
    token = (request.GET.get('token') or '').strip()
    if not token:
        return HttpResponse(
            '缺少 token 参数。用法: .../agent/bootstrap/?token=<token>\n',
            status=400,
            content_type='text/plain; charset=utf-8',
        )

    server = (request.GET.get('server') or '').strip().rstrip('/')
    if not server:
        # 根据当前请求推断对外地址
        host = request.get_host()
        scheme = 'https' if request.is_secure() else 'http'
        # X-Forwarded-Proto 兼容反向代理
        xf_proto = request.META.get('HTTP_X_FORWARDED_PROTO', '').split(',')[0].strip()
        if xf_proto in ('http', 'https'):
            scheme = xf_proto
        server = f'{scheme}://{host}'

    fmt = (request.GET.get('format') or 'sh').strip().lower()
    agent_url = f'{server}/api/gp_logcat/agent/'

    # shell 转义（单引号包裹）
    def _sq(s):
        return "'" + str(s).replace("'", "'\"'\"'") + "'"

    server_q = _sq(server)
    token_q = _sq(token)
    agent_url_q = _sq(agent_url)

    if fmt == 'bat':
        # Windows：检测 python / py，下载代理后启动
        content = (
            '@echo off\r\n'
            'chcp 65001 >nul\r\n'
            'setlocal\r\n'
            f'set "SERVER={server}"\r\n'
            f'set "TOKEN={token}"\r\n'
            'set "AGENT_DIR=%USERPROFILE%\\.gp_logcat"\r\n'
            'set "AGENT_SCRIPT=%AGENT_DIR%\\gp_logcat_agent.py"\r\n'
            'if not exist "%AGENT_DIR%" mkdir "%AGENT_DIR%"\r\n'
            'where python >nul 2>&1 && set "PY=python" || set "PY="\r\n'
            'if not defined PY where py >nul 2>&1 && set "PY=py -3"\r\n'
            'if not defined PY (\r\n'
            '  echo [错误] 未检测到 Python，请先安装 Python 3 并勾选 Add to PATH\r\n'
            '  pause\r\n'
            '  exit /b 1\r\n'
            ')\r\n'
            'if not exist "%AGENT_SCRIPT%" (\r\n'
            f'  echo [代理] 首次下载脚本: {agent_url}\r\n'
            f'  curl -fsSL "{agent_url}" -o "%AGENT_SCRIPT%"\r\n'
            '  if errorlevel 1 (\r\n'
            '    echo [错误] 下载代理脚本失败\r\n'
            '    pause\r\n'
            '    exit /b 1\r\n'
            '  )\r\n'
            ')\r\n'
            'echo [代理] Python 环境正常，正在启动...\r\n'
            '%PY% "%AGENT_SCRIPT%" --server "%SERVER%" --token "%TOKEN%"\r\n'
            'pause\r\n'
        )
        resp = HttpResponse(content, content_type='application/octet-stream')
        resp['Content-Disposition'] = 'attachment; filename="start_gp_logcat_agent.bat"'
        return resp

    # POSIX shell（macOS / Linux）；format=command 时加双击友好头
    shebang = '#!/bin/bash\n'
    if fmt == 'command':
        shebang = '#!/bin/bash\ncd "$(dirname "$0")"\n'

    content = (
        shebang
        + 'set -e\n'
        + f'SERVER={server_q}\n'
        + f'TOKEN={token_q}\n'
        + f'AGENT_URL={agent_url_q}\n'
        + 'AGENT_DIR="${HOME}/.gp_logcat"\n'
        + 'AGENT_SCRIPT="${AGENT_DIR}/gp_logcat_agent.py"\n'
        + '\n'
        + 'echo "[代理] 检查本地 Python 环境..."\n'
        + 'if ! command -v python3 >/dev/null 2>&1; then\n'
        + '  echo "[错误] 未检测到 python3，请先安装 Python 3"\n'
        + '  echo "  macOS: brew install python3"\n'
        + '  echo "  Ubuntu: sudo apt install python3"\n'
        + '  exit 1\n'
        + 'fi\n'
        + 'PY_VER=$(python3 -c "import sys; print(f\'{sys.version_info.major}.{sys.version_info.minor}\')")\n'
        + 'echo "[代理] 已找到 python3 (${PY_VER})"\n'
        + '\n'
        + 'mkdir -p "${AGENT_DIR}"\n'
        + 'if [ ! -f "${AGENT_SCRIPT}" ]; then\n'
        + '  echo "[代理] 首次下载代理脚本..."\n'
        + '  if command -v curl >/dev/null 2>&1; then\n'
        + '    curl -fsSL "${AGENT_URL}" -o "${AGENT_SCRIPT}"\n'
        + '  elif command -v wget >/dev/null 2>&1; then\n'
        + '    wget -qO "${AGENT_SCRIPT}" "${AGENT_URL}"\n'
        + '  else\n'
        + '    echo "[错误] 需要 curl 或 wget 以下载代理脚本"\n'
        + '    exit 1\n'
        + '  fi\n'
        + '  echo "[代理] 已保存到 ${AGENT_SCRIPT}"\n'
        + 'else\n'
        + '  echo "[代理] 已存在本地脚本，跳过下载"\n'
        + 'fi\n'
        + '\n'
        + 'echo "[代理] 启动中（保持本终端不关闭）..."\n'
        + 'echo "[代理] 服务器: ${SERVER}"\n'
        + 'exec python3 "${AGENT_SCRIPT}" --server "${SERVER}" --token "${TOKEN}"\n'
    )

    if fmt == 'command':
        resp = HttpResponse(content, content_type='application/octet-stream')
        resp['Content-Disposition'] = (
            'attachment; filename="start_gp_logcat_agent.command"'
        )
        return resp

    return HttpResponse(content, content_type='text/plain; charset=utf-8')
