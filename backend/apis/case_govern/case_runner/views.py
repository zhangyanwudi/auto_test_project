# -*- coding: utf-8 -*-
"""
巡检规范接口：explore（巡检试运行）、solidify（固化建用例）。

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
    """巡检试运行。

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


def _do_solidify(case_name, spec, creator='', goal=None):
    """把规范草稿固化为用例：建主表 + 按「模块 → 子功能 → 功能点」分层建节点树。

    节点树结构（precondition 挂根下，step/result 挂最底层功能点下）：
      根（module=用例名「巡检基建平台」）
        ├─ precondition（前置条件，页面地址）
        └─ 模块（如「达人管理」，node_type=case）
            └─ 子功能（如「上传达人」，node_type=case）
                └─ 功能点（如「批量上传」，node_type=case）
                    ├─ step × N
                    └─ result × M

    供 case_solidify 接口与 AI 助手「确认固化」共用。

    :param case_name: 用例名称
    :param spec:      规范草稿文本（含【precondition】/【step】/【result】三段）
    :param creator:   创建人（用户中文名或用户名）
    :param goal:      目标描述（用于解析模块/子功能/功能点层级；为空则退化为平铺）
    :return: (ok, data|error_msg)。ok 为 True 时 data 为 {'id': ..., 'case_name': ...}。
    """
    case_name = (case_name or '').strip()
    spec = (spec or '').strip()
    if not case_name or not spec:
        return False, '缺少 case_name 或 spec'

    nodes = _parse_spec_to_nodes(spec)
    if not nodes['precondition']:
        return False, '规范草稿中未提取到页面地址，无法固化'

    # 步骤/结果叶子节点
    step_nodes = [{'title': s, 'node_type': 'step', 'children': []} for s in nodes['steps']]
    result_nodes = [{'title': r, 'node_type': 'result', 'children': []} for r in nodes['results']]

    # 从目标描述解析层级：模块 → 子功能 → 功能点
    hierarchy = {'module': None, 'feature': None, 'action': None}
    if goal:
        from apps.case_govern.case_runner.explorer import parse_goal_hierarchy
        hierarchy = parse_goal_hierarchy(goal)

    # 把 step/result 挂到最底层功能点下；若没有功能点则挂到子功能；再没有则挂到模块；再没有则平铺挂根
    leaf_children = step_nodes + result_nodes

    action_children = []
    if hierarchy.get('action'):
        action_children = [{'title': hierarchy['action'], 'node_type': 'case', 'children': leaf_children}]
    elif hierarchy.get('feature'):
        action_children = leaf_children
    else:
        action_children = leaf_children

    feature_children = []
    if hierarchy.get('feature'):
        feature_children = [{'title': hierarchy['feature'], 'node_type': 'case', 'children': action_children}]
    elif hierarchy.get('action'):
        feature_children = action_children
    else:
        feature_children = action_children

    module_children = []
    if hierarchy.get('module'):
        module_children = [{'title': hierarchy['module'], 'node_type': 'case', 'children': feature_children}]
    else:
        module_children = feature_children

    # 根 children：前置条件 + 模块层级
    root_children = [{'title': nodes['precondition'], 'node_type': 'precondition', 'children': []}]
    root_children.extend(module_children)

    tree = {
        'id': None,
        'title': case_name,
        'node_type': 'module',
        'is_smoke': False,
        'exec_result': '',
        'collapsed': False,
        'image': '',
        'children': root_children,
    }

    from apis.case_govern.views import _normalize_node, _sync_case_nodes
    from django.db import transaction

    # 同名用例（case_name + module 唯一）已存在时，更新其节点树（幂等），而不是新建报唯一约束冲突。
    case, _created = ZCaseGovernCase.objects.get_or_create(
        case_name=case_name,
        module='',
        defaults={
            'priority': 2,
            'status': 1,
            'creator': creator,
            'description': '',
            'image': '',
        },
    )
    if not _created and creator:
        case.creator = creator
        case.save(update_fields=['creator'])

    with transaction.atomic():
        _sync_case_nodes(case.id, _normalize_node(tree))

    return True, {'id': case.id, 'case_name': case.case_name}


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

    creator = request.z_user.user_cn_name or request.z_user.user_name
    ok, result = _do_solidify(
        (body.get('case_name') or '').strip(),
        (body.get('spec') or '').strip(),
        creator=creator,
    )
    if not ok:
        return _fail(result)
    return _ok(result, '固化成功')
