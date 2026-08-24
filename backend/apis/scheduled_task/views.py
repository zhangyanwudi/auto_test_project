import json
import logging
import re

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.scheduled_task.executor import (
    CRON_5,
    build_run_result,
    execute_task_once,
    list_task_file_names,
    normalize_task_file_basename,
    parse_stored_run_detail,
    persist_task_run_result,
    task_file_allowed,
    validate_cron,
)
from apps.scheduled_task.models import ZScheduledTask
from apps.users.decorators import require_valid_token

logger = logging.getLogger(__name__)


def _serialize(t: ZScheduledTask):
    return {
        'id': t.id,
        'task_name': t.task_name,
        'task_code': t.task_code,
        'description': t.description or '',
        'cron_expression': t.cron_expression,
        'execution_type': getattr(t, 'execution_type', None) or 'file',
        'task_file_name': getattr(t, 'task_file_name', None) or '',
        'status': t.status,
        'last_run_time': t.last_run_time.isoformat() if t.last_run_time else None,
        'last_run_success': t.last_run_success,
        'last_run_message': t.last_run_message or '',
        'last_run_detail': parse_stored_run_detail(getattr(t, 'last_run_detail', None) or ''),
        'create_time': t.create_time.isoformat() if t.create_time else None,
        'update_time': t.update_time.isoformat() if t.update_time else None,
    }


def _parse_body(request):
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return None


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def task_list(request):
    """定时任务列表（按 id 倒序）。"""
    qs = ZScheduledTask.objects.all().order_by('-id')
    return JsonResponse({'code': 0, 'data': [_serialize(t) for t in qs]})


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def task_file_names(request):
    """列出 backend/task_file 目录下文件名（仅一层，不含子目录）。"""
    return JsonResponse({'code': 0, 'data': list_task_file_names()})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def task_create(request):
    """新增定时任务。"""
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    task_name = (body.get('task_name') or '').strip()
    task_code = (body.get('task_code') or '').strip()
    cron_expression = (body.get('cron_expression') or '').strip()
    if not task_name or not task_code:
        return JsonResponse({'code': 400, 'message': '任务名称与任务编码不能为空'}, status=400)
    err = validate_cron(cron_expression)
    if err:
        return JsonResponse({'code': 400, 'message': err}, status=400)
    if ZScheduledTask.objects.filter(task_code=task_code).exists():
        return JsonResponse({'code': 400, 'message': '任务编码已存在'}, status=400)
    execution_type = (body.get('execution_type') or 'file').strip() or 'file'
    if execution_type not in ('file', 'other'):
        return JsonResponse({'code': 400, 'message': 'execution_type 须为 file 或 other'}, status=400)
    task_file_name = normalize_task_file_basename((body.get('task_file_name') or '').strip())
    if execution_type == 'file':
        if not task_file_name:
            return JsonResponse({'code': 400, 'message': '文件执行类型下请选择执行文件'}, status=400)
        if not task_file_allowed(task_file_name):
            return JsonResponse({'code': 400, 'message': '执行文件不存在或非法'}, status=400)
    else:
        task_file_name = ''
    t = ZScheduledTask.objects.create(
        task_name=task_name,
        task_code=task_code,
        description=(body.get('description') or '').strip(),
        cron_expression=cron_expression,
        execution_type=execution_type,
        task_file_name=task_file_name,
        status=int(body.get('status') if body.get('status') is not None else 1),
    )
    return JsonResponse({'code': 0, 'message': '创建成功', 'data': _serialize(t)})


@csrf_exempt
@require_http_methods(['PUT'])
@require_valid_token
def task_update(request, pk):
    """更新定时任务（任务编码不可改）。"""
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    try:
        t = ZScheduledTask.objects.get(pk=pk)
    except ZScheduledTask.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '任务不存在'}, status=404)
    task_name = (body.get('task_name') or '').strip()
    cron_expression = (body.get('cron_expression') or '').strip()
    if not task_name:
        return JsonResponse({'code': 400, 'message': '任务名称不能为空'}, status=400)
    err = validate_cron(cron_expression)
    if err:
        return JsonResponse({'code': 400, 'message': err}, status=400)
    execution_type = body.get('execution_type')
    if execution_type is not None:
        execution_type = str(execution_type).strip() or 'file'
        if execution_type not in ('file', 'other'):
            return JsonResponse({'code': 400, 'message': 'execution_type 须为 file 或 other'}, status=400)
        t.execution_type = execution_type
    task_file_name = body.get('task_file_name')
    if task_file_name is not None:
        task_file_name = normalize_task_file_basename(str(task_file_name).strip())
    et = t.execution_type or 'file'
    if et == 'file':
        raw_name = task_file_name if task_file_name is not None else (t.task_file_name or '')
        name = normalize_task_file_basename(str(raw_name).strip())
        if not name:
            return JsonResponse({'code': 400, 'message': '文件执行类型下请选择执行文件'}, status=400)
        if not task_file_allowed(name):
            return JsonResponse({'code': 400, 'message': '执行文件不存在或非法'}, status=400)
        t.task_file_name = name
    else:
        t.task_file_name = ''
    t.task_name = task_name
    t.description = (body.get('description') or '').strip()
    t.cron_expression = cron_expression
    t.save()
    return JsonResponse({'code': 0, 'message': '保存成功', 'data': _serialize(t)})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def task_status(request, pk):
    """启用 / 停用：body { \"status\": 0|1 }"""
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    try:
        t = ZScheduledTask.objects.get(pk=pk)
    except ZScheduledTask.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '任务不存在'}, status=404)
    st = body.get('status')
    if st not in (0, 1) and st not in ('0', '1'):
        return JsonResponse({'code': 400, 'message': 'status 须为 0 或 1'}, status=400)
    t.status = int(st)
    t.save()
    return JsonResponse({'code': 0, 'message': '已更新', 'data': _serialize(t)})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def task_run_now(request, pk):
    """
    立即运行一次：按任务配置执行 task_file 下脚本，并刷新 last_run_time。
    可选 POST JSON：{"task_file_name": "test_run_task.py"} 覆盖本次运行的文件名（仍须在 task_file 目录下且通过校验）。
    """
    try:
        t = ZScheduledTask.objects.get(pk=pk)
    except ZScheduledTask.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '任务不存在'}, status=404)
    body = _parse_body(request) or {}
    override = body.get('task_file_name')
    if override is not None and str(override).strip() == '':
        override = None
    ok, msg, detail = execute_task_once(t, task_file_name_override=override)
    persist_task_run_result(t, ok, msg, detail)
    t.refresh_from_db()
    data = _serialize(t)
    run_result = build_run_result(ok, msg, detail)
    data['run_result'] = run_result
    return JsonResponse(
        {
            'code': 0,
            'message': run_result['message'],
            'data': data,
        }
    )


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def task_delete(request, pk):
    """删除任务。"""
    try:
        t = ZScheduledTask.objects.get(pk=pk)
    except ZScheduledTask.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '任务不存在'}, status=404)
    t.delete()
    return JsonResponse({'code': 0, 'message': '已删除'})
