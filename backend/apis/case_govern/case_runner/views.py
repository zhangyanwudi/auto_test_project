# -*- coding: utf-8 -*-
"""
巡检规范接口：explore（生成规范 + 试运行）、solidify（固化建用例）。

- explore：调 case_runner.runner.run_explore，返回「规范草稿 + 每步明细 + 通过/失败」
- solidify：用户确认后，把规范草稿建成用例（节点树写入 case_govern）
"""
import json
import re

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.users.decorators import require_valid_token
from apps.case_govern.models import ZCaseGovernCase, ZCaseGovernCaseNode


def _ok(data=None, msg='成功'):
    return JsonResponse({'code': 0, 'message': msg, 'data': data if data is not None else {}})


def _fail(msg, code=400, status=400):
    return JsonResponse({'code': code, 'message': msg}, status=status)


def _parse_body(request):
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return None


def _parse_spec_to_nodes(spec_text):
    """把规范草稿文本解析成 precondition/step/result 三段（与 runner 保持一致）。"""
    pre = ''
    steps = []
    results = []
    section = None
    for line in (spec_text or '').splitlines():
        s = line.strip()
        if '【precondition】' in s:
            section = 'pre'
            continue
        if '【step】' in s:
            section = 'step'
            continue
        if '【result】' in s:
            section = 'result'
            continue
        if not s or s.startswith('#') or s.startswith('```'):
            continue
        if section == 'pre':
            if s.startswith('http'):
                pre = s
        elif section == 'step':
            steps.append(s)
        elif section == 'result':
            results.append(s)
    return {'precondition': pre, 'steps': steps, 'results': results}


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def case_explore(request):
    """生成巡检规范 + 试运行。

    body: { description: "用户对页面和功能的自然语言描述" }
    返回: { spec, steps, passed, failed, total, error }
    """
    body = _parse_body(request)
    if body is None:
        return _fail('请求体格式错误')
    description = (body.get('description') or '').strip()
    if not description:
        return _fail('请提供要巡检的页面描述')

    from apps.case_govern.case_runner.runner import run_explore
    result = run_explore(description)
    return _ok(result)


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def case_solidify(request):
    """用户确认规范后，固化为用例（自动建节点树）。

    body: { case_name, spec }
    返回: 新建用例的 id + case_name
    """
    body = _parse_body(request)
    if body is None:
        return _fail('请求体格式错误')
    case_name = (body.get('case_name') or '').strip()
    spec = (body.get('spec') or '').strip()
    if not case_name or not spec:
        return _fail('缺少 case_name 或 spec')

    nodes = _parse_spec_to_nodes(spec)
    if not nodes['precondition']:
        return _fail('规范草稿中未提取到页面地址，无法固化')

    # 构建节点树：根（module=用例名） → 前置（precondition） → 步骤（step） → 结果（result）
    children = []
    # precondition 节点
    children.append({
        'title': nodes['precondition'],
        'node_type': 'precondition',
        'children': [],
    })
    # step 节点
    for s in nodes['steps']:
        children.append({'title': s, 'node_type': 'step', 'children': []})
    # result 节点
    for r in nodes['results']:
        children.append({'title': r, 'node_type': 'result', 'children': []})

    tree = {
        'id': None,
        'title': case_name,
        'node_type': 'module',
        'is_smoke': False,
        'exec_result': '',
        'collapsed': False,
        'image': '',
        'children': children,
    }

    case = ZCaseGovernCase.objects.create(
        case_name=case_name,
        module='',
        priority=2,
        status=1,
        creator=request.z_user.user_cn_name or request.z_user.user_name,
        description='',
        image='',
    )

    from apps.case_govern.views import _normalize_node, _sync_case_nodes
    from django.db import transaction
    with transaction.atomic():
        _sync_case_nodes(case.id, _normalize_node(tree))

    return _ok({'id': case.id, 'case_name': case.case_name}, '固化成功')
