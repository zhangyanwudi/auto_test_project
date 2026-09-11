import json
import logging
import re
from pathlib import Path

import pymysql
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.db_table_note.models import ZDbTableNote
from apps.users.decorators import require_valid_token

logger = logging.getLogger('apis.db_table_note')

# 连接配置（backend/config/db_table_note_config.json）
CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'db_table_note_config.json'


def _load_connections():
    """读取连接配置列表；失败返回空列表。"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('connections') or []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_connections(connections):
    """写回连接配置列表。"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump({'connections': connections}, f, ensure_ascii=False, indent=4)


def _parse_body(request):
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return None


def _connection_by_id(conn_id):
    for c in _load_connections():
        if str(c.get('id', '')) == str(conn_id):
            return c
    return None


def _public_connection(c):
    """返回给前端的连接信息（不含密码，只标记是否已配密码）。"""
    return {
        'id': c.get('id', ''),
        'name': c.get('name', ''),
        'host': c.get('host', ''),
        'port': c.get('port', 3306),
        'user': c.get('user', ''),
        'database': c.get('database', ''),
        'has_password': bool(c.get('password', '')),
    }


def _open_conn(cfg):
    """用连接配置建立 pymysql 连接（autocommit=True）。"""
    port = cfg.get('port')
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 3306
    return pymysql.connect(
        host=cfg.get('host', ''),
        port=port,
        user=cfg.get('user', ''),
        password=cfg.get('password', ''),
        database=cfg.get('database', ''),
        charset='utf8mb4',
        autocommit=True,
    )


def _table_note_public(m):
    return {
        'id': m.id,
        'connection_id': m.connection_id,
        'table_name': m.table_name,
        'note': m.note or '',
        'sql_records': m.sql_records or '',
        'field_notes': m.field_notes or '',
        'update_time': m.update_time.strftime('%Y-%m-%d %H:%M:%S'),
    }


def _parse_field_notes(field_notes):
    """解析字段手动备注 JSON 字符串为 dict；失败返回空 dict。"""
    if not field_notes:
        return {}
    try:
        data = json.loads(field_notes)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _fetch_table_columns(cfg, table_name):
    """读取某表全部字段：字段名 + 字段注释（按 ORDINAL_POSITION 排序）。"""
    conn = _open_conn(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT column_name, column_comment '
                'FROM information_schema.columns '
                'WHERE table_schema = %s AND table_name = %s '
                'ORDER BY ordinal_position',
                (cfg.get('database', ''), table_name),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{'name': name, 'comment': comment or ''} for name, comment in rows]


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def connection_list(request):
    """连接列表（脱敏，不回传密码）。"""
    return JsonResponse({'code': 0, 'data': [_public_connection(c) for c in _load_connections()]})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def connection_save(request):
    """新增/编辑连接配置；编辑时 password 留空表示保持原密码不变。"""
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    conn_id = (body.get('id') or '').strip()
    host = (body.get('host') or '').strip()
    user = (body.get('user') or '').strip()
    database = (body.get('database') or '').strip()
    if not conn_id:
        return JsonResponse({'code': 400, 'message': '连接标识不能为空'}, status=400)
    if not host or not user or not database:
        return JsonResponse({'code': 400, 'message': '地址、用户名、数据库不能为空'}, status=400)

    connections = _load_connections()
    idx = next((i for i, c in enumerate(connections) if str(c.get('id', '')) == conn_id), None)

    port = body.get('port') or 3306
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 3306

    if idx is None:
        # 新增：密码必填
        password = (body.get('password') or '').strip()
        if not password:
            return JsonResponse({'code': 400, 'message': '新增连接时密码不能为空'}, status=400)
        new_item = {
            'id': conn_id,
            'name': (body.get('name') or '').strip() or conn_id,
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database,
        }
        connections.append(new_item)
    else:
        old = connections[idx]
        password = (body.get('password') or '').strip()
        if not password:
            password = old.get('password', '')  # 留空保持原密码
        connections[idx] = {
            'id': conn_id,
            'name': (body.get('name') or '').strip() or old.get('name', '') or conn_id,
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database,
        }

    _save_connections(connections)
    return JsonResponse({'code': 0, 'message': '保存成功'})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def connection_delete(request):
    """删除连接配置。"""
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    conn_id = (body.get('id') or '').strip()
    if not conn_id:
        return JsonResponse({'code': 400, 'message': '连接标识不能为空'}, status=400)
    connections = [c for c in _load_connections() if str(c.get('id', '')) != conn_id]
    _save_connections(connections)
    return JsonResponse({'code': 0, 'message': '已删除'})


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def table_list(request):
    """获取连接下所有表（表名 + 表注释），附该表是否已有备注。

    表注释优先使用本地手动备注（note），否则回退数据库表注释：
    - 手动备注过某表后，重新引入/刷新该库时手动备注不丢失（仍显示手动备注）。
    - 备注值存储于主库 z_db_table_note，与数据库本身注释解耦。
    """
    conn_id = (request.GET.get('connection_id') or '').strip()
    keyword = (request.GET.get('keyword') or '').strip()
    cfg = _connection_by_id(conn_id)
    if not cfg:
        return JsonResponse({'code': 404, 'message': '连接配置不存在'}, status=404)

    try:
        conn = _open_conn(cfg)
    except Exception as e:
        logger.exception('连接数据库失败: %s', conn_id)
        return JsonResponse({'code': 500, 'message': '连接数据库失败：%s' % e}, status=500)

    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT table_name, table_comment '
                'FROM information_schema.tables '
                'WHERE table_schema = %s ORDER BY table_name',
                (cfg.get('database', ''),),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    # 本地手动备注：表名 -> {note, sql_records, field_notes}
    note_map = {
        m.table_name: m
        for m in ZDbTableNote.objects.filter(connection_id=conn_id)
    }
    data = []
    for table_name, table_comment in rows:
        m = note_map.get(table_name)
        # 手动备注优先，空则回退数据库注释
        note = (m.note or '') if m else ''
        sql_records = (m.sql_records or '') if m else ''
        field_notes = (m.field_notes or '') if m else ''
        comment = note.strip() or (table_comment or '')
        if keyword and keyword.lower() not in str(table_name).lower() \
                and keyword not in comment:
            continue
        data.append({
            'table_name': table_name,
            'comment': comment,
            'db_comment': table_comment or '',
            'note': note,
            'sql_records': sql_records,
            'field_notes': field_notes,
            'has_note': table_name in note_map,
        })
    return JsonResponse({'code': 0, 'data': data})


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def table_fields(request):
    """按需加载某表的字段注释（默认不展示，手动触发时调用）。

    返回每字段：name / comment（数据库注释）/ manual（手动备注）/ final_comment（拼接结果）。
    拼接规则：手动备注 优先于 数据库注释。
    """
    conn_id = (request.GET.get('connection_id') or '').strip()
    table_name = (request.GET.get('table_name') or '').strip()
    if not conn_id or not table_name:
        return JsonResponse({'code': 400, 'message': '缺少 connection_id 或 table_name'}, status=400)
    cfg = _connection_by_id(conn_id)
    if not cfg:
        return JsonResponse({'code': 404, 'message': '连接配置不存在'}, status=404)

    try:
        columns = _fetch_table_columns(cfg, table_name)
    except Exception as e:
        logger.exception('读取字段失败: %s/%s', conn_id, table_name)
        return JsonResponse({'code': 500, 'message': '读取字段失败：%s' % e}, status=500)

    try:
        m = ZDbTableNote.objects.get(connection_id=conn_id, table_name=table_name)
        manual_map = _parse_field_notes(m.field_notes)
    except ZDbTableNote.DoesNotExist:
        manual_map = {}

    data = []
    for col in columns:
        name = col['name']
        manual = (manual_map.get(name) or '').strip()
        final = manual or (col['comment'] or '')
        data.append({
            'name': name,
            'comment': col['comment'],
            'manual': manual,
            'final_comment': final,
        })
    return JsonResponse({'code': 0, 'data': data})


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def note_get(request):
    """获取某连接某表的备注与执行 SQL。"""
    conn_id = (request.GET.get('connection_id') or '').strip()
    table_name = (request.GET.get('table_name') or '').strip()
    if not conn_id or not table_name:
        return JsonResponse({'code': 400, 'message': '缺少 connection_id 或 table_name'}, status=400)
    try:
        m = ZDbTableNote.objects.get(connection_id=conn_id, table_name=table_name)
    except ZDbTableNote.DoesNotExist:
        return JsonResponse({'code': 0, 'data': {'note': '', 'sql_records': '', 'field_notes': ''}})
    return JsonResponse({'code': 0, 'data': _table_note_public(m)})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def note_save(request):
    """保存某连接某表的备注、执行 SQL 及字段手动备注（未传字段保持原值）。"""
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    conn_id = (body.get('connection_id') or '').strip()
    table_name = (body.get('table_name') or '').strip()
    if not conn_id or not table_name:
        return JsonResponse({'code': 400, 'message': '缺少 connection_id 或 table_name'}, status=400)

    try:
        m = ZDbTableNote.objects.get(connection_id=conn_id, table_name=table_name)
    except ZDbTableNote.DoesNotExist:
        m = None

    # 未传入的字段保持原值，避免部分更新时清空其它内容
    note = m.note if m else ''
    sql_records = m.sql_records if m else ''
    field_notes = m.field_notes if m else ''

    if 'note' in body:
        note = (body.get('note') or '').strip()
    if 'sql_records' in body:
        sql_records = (body.get('sql_records') or '').strip()
    if 'field_notes' in body:
        f = body.get('field_notes')
        if isinstance(f, dict):
            field_notes = json.dumps(f, ensure_ascii=False)
        else:
            field_notes = (f or '').strip()

    m, _ = ZDbTableNote.objects.update_or_create(
        connection_id=conn_id,
        table_name=table_name,
        defaults={
            'note': note,
            'sql_records': sql_records,
            'field_notes': field_notes,
        },
    )
    return JsonResponse({'code': 0, 'message': '保存成功', 'data': _table_note_public(m)})
