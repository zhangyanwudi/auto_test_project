import json
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from apps.menu_management.models import ZMenu
from apps.users.decorators import require_valid_token, require_super_admin


def _link_new_menu_to_super_admin(menu):
    """新增菜单后，超级管理员角色默认勾选该菜单（z_role_menu）。"""
    from apps.role_management.models import ZRole, ZRoleMenu

    role, _ = ZRole.objects.get_or_create(
        role_code='super_admin',
        defaults={
            'role_name': '超级管理员',
            'remark': '默认拥有全部菜单',
            'status': 1,
        },
    )
    ZRoleMenu.objects.get_or_create(role=role, menu=menu)


def _first_user_id():
    """id 最小的用户（系统管理员），侧栏显示全部菜单"""
    from apps.users.models import ZUser
    return ZUser.objects.order_by('id').values_list('id', flat=True).first()


def _expand_menu_ids_with_parents(menu_ids):
    """
    角色仅勾选了子菜单时，补全父级 id，否则侧栏树无法展示分组。
    menu_ids: 可迭代的菜单主键集合
    """
    if not menu_ids:
        return set()
    ids = set(int(x) for x in menu_ids)
    # 仅取启用菜单的 id -> parent_id，向上补全
    rows = list(ZMenu.objects.filter(status=1).values_list('id', 'parent_id'))
    parent_map = {mid: pid for mid, pid in rows}
    changed = True
    while changed:
        changed = False
        for mid in list(ids):
            pid = parent_map.get(mid)
            if pid and pid not in ids:
                ids.add(pid)
                changed = True
    return ids


def _sidebar_menu_ids_for_user(user):
    """
    侧栏（enabled_only=1）允许的菜单主键；无权限则空集合。
    第一条用户、或角色 super_admin：全部启用菜单（调用方再 filter）。
    """
    if not user:
        return None  # 不应出现，装饰器已校验
    if user.id == _first_user_id():
        return None  # None 表示不限制，返回全部启用菜单

    rid = getattr(user, 'role_id', None)
    if not rid:
        return set()

    from apps.role_management.models import ZRole, ZRoleMenu

    try:
        role = ZRole.objects.get(pk=rid)
    except ZRole.DoesNotExist:
        return set()

    if role.role_code == 'super_admin':
        return None

    raw = list(ZRoleMenu.objects.filter(role=role).values_list('menu_id', flat=True))
    return _expand_menu_ids_with_parents(raw)


def _serialize_menu(m):
    return {
        'id': m.id,
        'menu_name': m.menu_name,
        'menu_code': m.menu_code,
        'path': m.path or '',
        'parent_id': m.parent_id,
        'icon': m.icon or '',
        'sort_order': m.sort_order,
        'status': m.status,
        'create_time': m.create_time.isoformat() if m.create_time else None,
        'update_time': m.update_time.isoformat() if m.update_time else None,
    }


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def menu_list(request):
    """
    菜单列表。
    查询参数 enabled_only=1：仅返回启用(status=1)，供侧栏使用；
    此时按当前登录用户角色过滤（z_role_menu），第一条用户 / super_admin 角色仍看全部。
    无 enabled_only 时返回全量（菜单管理页维护用）。
    """
    # 按「排序」字段从小到大（sort_order ASC）；相同排序号时按 id 升序
    qs = ZMenu.objects.all().order_by('sort_order', 'id')
    enabled_only = request.GET.get('enabled_only') == '1'
    if enabled_only:
        qs = qs.filter(status=1)
        user = getattr(request, 'z_user', None)
        allowed = _sidebar_menu_ids_for_user(user)
        if allowed is not None:
            qs = qs.filter(id__in=allowed)
    return JsonResponse({'code': 0, 'data': [_serialize_menu(m) for m in qs]})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def menu_create(request):
    """新增菜单"""
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    menu_name = (body.get('menu_name') or '').strip()
    menu_code = (body.get('menu_code') or '').strip()
    if not menu_name or not menu_code:
        return JsonResponse({'code': 400, 'message': '菜单名称与菜单编码不能为空'}, status=400)
    if ZMenu.objects.filter(menu_code=menu_code).exists():
        return JsonResponse({'code': 400, 'message': '菜单编码已存在'}, status=400)
    parent_id = body.get('parent_id')
    parent = None
    if parent_id not in (None, '', 0, '0'):
        try:
            parent = ZMenu.objects.get(pk=int(parent_id))
        except (ZMenu.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'code': 400, 'message': '父菜单不存在'}, status=400)
    with transaction.atomic():
        m = ZMenu.objects.create(
            menu_name=menu_name,
            menu_code=menu_code,
            path=(body.get('path') or '').strip(),
            parent=parent,
            icon=(body.get('icon') or '').strip(),
            sort_order=int(body.get('sort_order') or 0),
            status=int(body.get('status') if body.get('status') is not None else 1),
        )
        _link_new_menu_to_super_admin(m)
    return JsonResponse({'code': 0, 'message': '创建成功', 'data': _serialize_menu(m)})


@csrf_exempt
@require_http_methods(['PUT', 'PATCH'])
@require_valid_token
def menu_update(request, pk):
    """编辑菜单"""
    try:
        m = ZMenu.objects.get(pk=pk)
    except ZMenu.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '菜单不存在'}, status=404)
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    if 'menu_name' in body:
        m.menu_name = (body.get('menu_name') or '').strip()
    if 'menu_code' in body:
        code = (body.get('menu_code') or '').strip()
        if code and ZMenu.objects.exclude(pk=m.pk).filter(menu_code=code).exists():
            return JsonResponse({'code': 400, 'message': '菜单编码已存在'}, status=400)
        if code:
            m.menu_code = code
    if 'path' in body:
        m.path = (body.get('path') or '').strip()
    if 'icon' in body:
        m.icon = (body.get('icon') or '').strip()
    if 'sort_order' in body:
        m.sort_order = int(body.get('sort_order') or 0)
    if 'status' in body:
        m.status = int(body.get('status'))
    if 'parent_id' in body:
        pid = body.get('parent_id')
        if pid is None or pid == '':
            m.parent = None
        else:
            if int(pid) == m.id:
                return JsonResponse({'code': 400, 'message': '不能将自身设为父菜单'}, status=400)
            try:
                m.parent = ZMenu.objects.get(pk=pid)
            except ZMenu.DoesNotExist:
                return JsonResponse({'code': 400, 'message': '父菜单不存在'}, status=400)
    m.save()
    return JsonResponse({'code': 0, 'message': '保存成功', 'data': _serialize_menu(m)})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def menu_status(request, pk):
    """停用/启用：body { \"status\": 0|1 }"""
    try:
        m = ZMenu.objects.get(pk=pk)
    except ZMenu.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '菜单不存在'}, status=404)
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    st = body.get('status')
    if st not in (0, 1):
        return JsonResponse({'code': 400, 'message': 'status 须为 0 或 1'}, status=400)
    m.status = int(st)
    m.save(update_fields=['status', 'update_time'])
    return JsonResponse({'code': 0, 'message': '已更新', 'data': _serialize_menu(m)})


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
@require_valid_token
@require_super_admin
def menu_delete(request, pk):
    """删除菜单：仅允许已停用(status=0)，且不能有子菜单（避免误删级联）。"""
    try:
        m = ZMenu.objects.get(pk=pk)
    except ZMenu.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '菜单不存在'}, status=404)
    if m.status != 0:
        return JsonResponse({'code': 400, 'message': '仅已停用的菜单可删除，请先停用'}, status=400)
    if m.children.exists():
        return JsonResponse(
            {'code': 400, 'message': '存在子菜单，请先删除或移走子菜单后再删除本菜单'},
            status=400,
        )
    m.delete()
    return JsonResponse({'code': 0, 'message': '已删除'})
