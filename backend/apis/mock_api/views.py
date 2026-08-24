"""
Mock API 管理 — 规则 CRUD、代理启停、数据库连接配置
====================================================
- 规则管理：增删改查 + 状态切换
- 代理控制：启动 / 停止 / 状态 / 热加载规则
- 数据库连接配置：可复用的数据库连接
"""
import json
import logging
import os
import signal
import subprocess
import time

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from apps.mock_api.models import ZMockApiRule, ZMockApiDbConfig
from apps.users.decorators import require_valid_token

logger = logging.getLogger('apis.mock_api')


# ============================================================
# 工具函数
# ============================================================

def _serialize_rule(rule):
    """序列化 Mock 规则为字典"""
    return {
        'id': rule.id,
        'rule_name': rule.rule_name,
        'url_pattern': rule.url_pattern,
        'match_type': rule.match_type,
        'response_file': rule.response_file or '',
        'response_data': rule.response_data or '',
        'response_sql': rule.response_sql or '',
        'response_db': rule.response_db or '',
        'status_code': rule.status_code,
        'status': rule.status,
        'sort_order': rule.sort_order,
        'remark': rule.remark or '',
        'create_time': rule.create_time.isoformat() if rule.create_time else None,
        'update_time': rule.update_time.isoformat() if rule.update_time else None,
    }


def _serialize_db_config(cfg):
    """序列化数据库连接配置为字典（隐藏密码）"""
    return {
        'id': cfg.id,
        'config_key': cfg.config_key,
        'db_type': cfg.db_type,
        'host': cfg.host,
        'port': cfg.port,
        'username': cfg.username,
        'password': '******',  # 不回显原始密码
        'database': cfg.database,
        'status': cfg.status,
        'remark': cfg.remark or '',
        'create_time': cfg.create_time.isoformat() if cfg.create_time else None,
        'update_time': cfg.update_time.isoformat() if cfg.update_time else None,
    }


def _ok(data=None, msg='成功'):
    """返回成功响应。data 为 None 时用空字典兜底（兼容旧调用方），
    但保留 list/dict 等非 None 的原值，避免空列表被 or 吞掉。"""
    return JsonResponse({'code': 0, 'message': msg, 'data': data if data is not None else {}})


def _fail(msg, code=400, status=400):
    return JsonResponse({'code': code, 'message': msg}, status=status)


# ============================================================
# 规则管理 CRUD
# ============================================================

@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def mock_rule_list(request):
    """Mock 规则列表（支持 ?status=1 过滤启用）"""
    qs = ZMockApiRule.objects.all().order_by('sort_order', 'id')
    status_filter = request.GET.get('status')
    if status_filter in ('0', '1'):
        qs = qs.filter(status=int(status_filter))
    return _ok([_serialize_rule(r) for r in qs])


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def mock_rule_create(request):
    """新增 Mock 规则"""
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _fail('请求体格式错误')

    rule_name = (body.get('rule_name') or '').strip()
    url_pattern = (body.get('url_pattern') or '').strip()
    if not rule_name or not url_pattern:
        return _fail('规则名称与 URL 模式不能为空')

    rule = ZMockApiRule.objects.create(
        rule_name=rule_name,
        url_pattern=url_pattern,
        match_type=body.get('match_type', 'contains'),
        response_file=(body.get('response_file') or '').strip(),
        response_data=(body.get('response_data') or '').strip(),
        response_sql=(body.get('response_sql') or '').strip(),
        response_db=(body.get('response_db') or '').strip(),
        status_code=int(body.get('status_code') or 200),
        status=int(body.get('status') if body.get('status') is not None else 1),
        sort_order=int(body.get('sort_order') or 0),
        remark=(body.get('remark') or '').strip(),
    )
    logger.info(f'[MockApi] 创建规则: {rule.rule_name} (id={rule.id})')
    _sync_rules_if_proxy_running()
    return _ok(_serialize_rule(rule), '创建成功')


@csrf_exempt
@require_http_methods(['PUT', 'PATCH'])
@require_valid_token
def mock_rule_update(request, pk):
    """编辑 Mock 规则"""
    try:
        rule = ZMockApiRule.objects.get(pk=pk)
    except ZMockApiRule.DoesNotExist:
        return _fail('规则不存在', code=404, status=404)

    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _fail('请求体格式错误')

    updatable = [
        'rule_name', 'url_pattern', 'match_type', 'response_file',
        'response_data', 'response_sql', 'response_db', 'remark',
    ]
    for field in updatable:
        if field in body:
            setattr(rule, field, (body.get(field) or '').strip() if isinstance(body.get(field), str) else body.get(field))
    if 'status_code' in body:
        rule.status_code = int(body.get('status_code') or 200)
    if 'status' in body:
        rule.status = int(body.get('status'))
    if 'sort_order' in body:
        rule.sort_order = int(body.get('sort_order') or 0)

    rule.save()
    logger.info(f'[MockApi] 更新规则: {rule.rule_name} (id={rule.id})')
    _sync_rules_if_proxy_running()
    return _ok(_serialize_rule(rule), '保存成功')


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def mock_rule_status(request, pk):
    """启用/停用规则: body { "status": 0|1 }"""
    try:
        rule = ZMockApiRule.objects.get(pk=pk)
    except ZMockApiRule.DoesNotExist:
        return _fail('规则不存在', code=404, status=404)

    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _fail('请求体格式错误')
    st = body.get('status')
    if st not in (0, 1):
        return _fail('status 须为 0 或 1')
    rule.status = int(st)
    rule.save(update_fields=['status', 'update_time'])
    logger.info(f'[MockApi] 规则状态变更: {rule.rule_name} (id={rule.id}) status={st}')
    # 代理运行中时热同步：停用规则立刻从内存移除，其余启用规则继续拦截
    synced = _sync_rules_if_proxy_running()
    msg = '已更新'
    if synced is not None:
        msg = f'已更新，并已同步 {synced} 条启用规则到代理'
    return _ok(_serialize_rule(rule), msg)


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
@require_valid_token
def mock_rule_delete(request, pk):
    """删除 Mock 规则（仅已停用可删除）"""
    try:
        rule = ZMockApiRule.objects.get(pk=pk)
    except ZMockApiRule.DoesNotExist:
        return _fail('规则不存在', code=404, status=404)
    if rule.status != 0:
        return _fail('仅已停用的规则可删除，请先停用')
    rule.delete()
    logger.info(f'[MockApi] 删除规则: {rule.rule_name} (id={pk})')
    _sync_rules_if_proxy_running()
    return _ok({}, '已删除')


# ============================================================
# 代理启停控制
# ============================================================

def _get_proxy_server():
    """获取全局 MockApiServer 实例（内部导入避免循环依赖）"""
    try:
        from base_utils.mock_api_utils import get_server
        return get_server()
    except Exception as e:
        logger.error(f'[MockApi] 获取代理实例失败: {e}')
        return None


def _sync_rules_to_proxy(server):
    """将数据库中的启用规则同步到代理实例（复用 MockApiServer.load_rules_from_db）"""
    if server is None:
        return 0
    rules = ZMockApiRule.objects.filter(status=1).order_by('sort_order', 'id')
    count = server.load_rules_from_db(rules)
    logger.info(f'[MockApi] 已同步 {count} 条规则到代理')
    return count


def _sync_rules_if_proxy_running():
    """代理运行中时，将当前启用规则热同步到内存（停用规则立即不再拦截）"""
    server = _get_proxy_server()
    if server is None or not server.is_running():
        return None
    return _sync_rules_to_proxy(server)


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def mock_proxy_start(request):
    """启动 Mock API 代理服务。

    Body 可选: { "port": 8080, "host": "0.0.0.0" }
    如已有运行中的代理则先停止再启动。
    """
    from base_utils.mock_api_utils import MockApiServer

    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        body = {}

    port = int(body.get('port') or 8080)
    host = body.get('host', '0.0.0.0')

    import base_utils.mock_api_utils as mu

    # 先停止旧实例（含残留线程），避免泄漏监听端口导致无法再次启动
    server = _get_proxy_server()
    if server is not None:
        server.stop()
        mu._server_instance = None

    # 仅创建一个实例并重试启动，避免失败重试时反复 new 导致孤儿线程占端口
    server = MockApiServer(port=port, host=host)
    mu._server_instance = server
    _sync_rules_to_proxy(server)

    last_err = f'端口 {port} 已被占用，请更换端口或先停止占用该端口的进程'
    for attempt in range(5):
        if attempt > 0:
            time.sleep(0.5)
            server.stop()
            if not server.wait_until_port_free(timeout=3.0):
                _kill_process_on_port(port)
                server.wait_until_port_free(timeout=2.0)

        if server.start(blocking=False):
            logger.info(f'[MockApi] 代理已启动: {host}:{port}')
            return _ok({'host': host, 'port': port, 'running': True}, f'代理已启动，监听 {host}:{port}')

        err = getattr(server, '_start_error', None)
        if err:
            last_err = err

    return _fail(last_err, code=500, status=500)


def _kill_process_on_port(port):
    """杀掉占用端口的进程（排除当前进程自身），返回杀掉的 PID 列表。"""
    my_pid = str(os.getpid())
    killed = []
    try:
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True, text=True, timeout=5,
        )
        pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
        for pid in pids:
            if pid == my_pid:
                continue  # 不杀自己（Django + mitmproxy 同进程时）
            try:
                os.kill(int(pid), signal.SIGKILL)
                killed.append(pid)
                logger.info(f'[MockApi] 已强制终止占用端口 {port} 的外部进程 PID={pid}')
            except Exception as e:
                logger.warning(f'[MockApi] 终止 PID={pid} 失败: {e}')
        if killed:
            time.sleep(0.5)
    except Exception as e:
        logger.error(f'[MockApi] lsof 查询端口 {port} 失败: {e}')
    return killed


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def mock_proxy_stop(request):
    """停止 Mock API 代理服务。

    优先通过托管实例停止；若实例不可用（如 CLI 独立启动），
    则直接杀掉占用端口的进程。
    """
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        body = {}
    port = int(body.get('port') or 8080)

    import base_utils.mock_api_utils as mu

    server = _get_proxy_server()
    stopped = False

    # 方式1：托管实例停止（即使 is_running 为 False，也尝试回收残留线程/端口）
    if server is not None:
        was_active = server.is_running() or (
            getattr(server, '_thread', None) is not None and server._thread.is_alive()
        ) or getattr(server, '_master', None) is not None
        server.stop()
        mu._server_instance = None
        if was_active:
            stopped = True
            logger.info('[MockApi] 代理已通过托管实例停止')

    # 方式2：兜底 — 杀掉外部进程（仅用于 CLI 独立启动的代理，排除当前进程）
    if not stopped:
        killed = _kill_process_on_port(port)
        if killed:
            stopped = True

    if stopped:
        return _ok({'running': False, 'port': port}, '代理已停止')
    else:
        return _ok({'running': False, 'port': port}, '未检测到运行中的代理')


def _is_port_listening(port, host='127.0.0.1'):
    """探测端口是否有进程在监听（用于识别 CLI 独立启动的代理）"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, int(port))) == 0
    except OSError:
        return False


@require_http_methods(['GET'])
@require_valid_token
def mock_proxy_status(request):
    """查询代理状态。

    优先看 Django 进程内托管实例；若无，再探测默认端口是否在监听
    （覆盖 scripts/start_mock_proxy.py 独立进程场景）。
    """
    port = int(request.GET.get('port') or 8080)
    server = _get_proxy_server()
    in_process = server is not None and server.is_running()
    port_listening = _is_port_listening(port) if not in_process else True
    running = in_process or port_listening
    rule_count = len(server.get_rules()) if server is not None else 0
    db_rule_count = ZMockApiRule.objects.filter(status=1).count()
    return _ok({
        'running': running,
        'in_process': in_process,
        'port': port,
        'proxy_rule_count': rule_count,
        'db_rule_count': db_rule_count,
        'db_config_count': ZMockApiDbConfig.objects.filter(status=1).count(),
    })


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def mock_proxy_reload(request):
    """热加载规则：从数据库重新同步启用规则到代理"""
    server = _get_proxy_server()
    if server is None or not server.is_running():
        return _fail('代理未运行，请先启动代理')
    count = _sync_rules_to_proxy(server)
    return _ok({'synced': count}, f'已同步 {count} 条规则')


# ============================================================
# 数据库连接配置管理
# ============================================================

@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def mock_db_config_list(request):
    """数据库连接配置列表"""
    qs = ZMockApiDbConfig.objects.all()
    return _ok([_serialize_db_config(c) for c in qs])


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def mock_db_config_create(request):
    """新增数据库连接配置"""
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _fail('请求体格式错误')

    config_key = (body.get('config_key') or '').strip()
    host = (body.get('host') or '').strip()
    if not config_key or not host:
        return _fail('连接标识与主机地址不能为空')
    if ZMockApiDbConfig.objects.filter(config_key=config_key).exists():
        return _fail('连接标识已存在')

    cfg = ZMockApiDbConfig.objects.create(
        config_key=config_key,
        db_type=body.get('db_type', 'mysql').strip(),
        host=host,
        port=int(body.get('port') or 3306),
        username=(body.get('username') or 'root').strip(),
        password=(body.get('password') or '').strip(),
        database=(body.get('database') or '').strip(),
        status=int(body.get('status') if body.get('status') is not None else 1),
        remark=(body.get('remark') or '').strip(),
    )
    logger.info(f'[MockApi] 创建数据库配置: {cfg.config_key} (id={cfg.id})')
    return _ok(_serialize_db_config(cfg), '创建成功')


@csrf_exempt
@require_http_methods(['PUT', 'PATCH'])
@require_valid_token
def mock_db_config_update(request, pk):
    """编辑数据库连接配置"""
    try:
        cfg = ZMockApiDbConfig.objects.get(pk=pk)
    except ZMockApiDbConfig.DoesNotExist:
        return _fail('配置不存在', code=404, status=404)

    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _fail('请求体格式错误')

    updatable_str = ['config_key', 'db_type', 'host', 'username', 'database', 'remark']
    for field in updatable_str:
        if field in body:
            setattr(cfg, field, (body.get(field) or '').strip())
    if 'port' in body:
        cfg.port = int(body.get('port') or 3306)
    if 'password' in body and body['password']:
        cfg.password = body['password'].strip()
    if 'status' in body:
        cfg.status = int(body.get('status'))

    cfg.save()
    return _ok(_serialize_db_config(cfg), '保存成功')


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
@require_valid_token
def mock_db_config_delete(request, pk):
    """删除数据库连接配置"""
    try:
        cfg = ZMockApiDbConfig.objects.get(pk=pk)
    except ZMockApiDbConfig.DoesNotExist:
        return _fail('配置不存在', code=404, status=404)
    cfg.delete()
    logger.info(f'[MockApi] 删除数据库配置: {cfg.config_key} (id={pk})')
    return _ok({}, '已删除')


# ============================================================
# 规则测试
# ============================================================

@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def mock_rule_test_match(request):
    """测试 URL 匹配规则。

    Body: { "url": "https://example.com/api/test", "rule_id": 123 }
    或:   { "url": "...", "url_pattern": "...", "match_type": "contains" }

    返回匹配结果及（如匹配到已存规则）响应数据预览。
    """
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _fail('请求体格式错误')

    test_url = (body.get('url') or '').strip()
    if not test_url:
        return _fail('请输入测试 URL')

    rule_id = body.get('rule_id')
    matched = False
    match_rule = None

    if rule_id:
        try:
            rule = ZMockApiRule.objects.get(pk=int(rule_id))
        except (ZMockApiRule.DoesNotExist, ValueError, TypeError):
            return _fail('规则不存在', code=404, status=404)
        from base_utils.mock_api_utils import _match_url
        matched = _match_url(test_url, rule.url_pattern, rule.match_type)
        if matched:
            match_rule = rule
    else:
        # 测试自定义模式
        url_pattern = (body.get('url_pattern') or '').strip()
        match_type = body.get('match_type', 'contains')
        if not url_pattern:
            return _fail('请指定规则或提供 url_pattern')
        from base_utils.mock_api_utils import _match_url
        matched = _match_url(test_url, url_pattern, match_type)

    result = {
        'matched': matched,
        'test_url': test_url,
    }
    if match_rule:
        result['rule'] = _serialize_rule(match_rule)
    return _ok(result)
