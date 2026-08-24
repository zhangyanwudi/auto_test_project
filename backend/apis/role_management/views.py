import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction

from apps.role_management.models import ZRole, ZRoleMenu
from apps.menu_management.models import ZMenu
from apps.users.decorators import require_valid_token, require_super_admin


def _serialize_role(r, menu_ids=None):
    row = {
        'id': r.id,
        'role_name': r.role_name,
        'role_code': r.role_code,
        'remark': r.remark or '',
        'status': r.status,
        'create_time': r.create_time.isoformat() if r.create_time else None,
        'update_time': r.update_time.isoformat() if r.update_time else None,
    }
    if menu_ids is not None:
        row['menu_ids'] = menu_ids
    else:
        row['menu_ids'] = list(
            ZRoleMenu.objects.filter(role=r).values_list('menu_id', flat=True)
        )
    return row


def _set_role_menus(role, menu_ids):
    """替换角色的菜单关联"""
    ZRoleMenu.objects.filter(role=role).delete()
    if not menu_ids:
        return
    for mid in menu_ids:
        try:
            m = ZMenu.objects.get(pk=mid)
            if m.status == 1:
                ZRoleMenu.objects.get_or_create(role=role, menu=m)
        except ZMenu.DoesNotExist:
            pass


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def role_list(request):
    qs = ZRole.objects.all().order_by('id')
    data = [_serialize_role(r) for r in qs]
    return JsonResponse({'code': 0, 'data': data})


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def menu_options(request):
    """供角色勾选：全部启用菜单"""
    qs = ZMenu.objects.filter(status=1).order_by('sort_order', 'id')
    data = [
        {
            'id': m.id,
            'menu_name': m.menu_name,
            'menu_code': m.menu_code,
            'parent_id': m.parent_id,
        }
        for m in qs
    ]
    return JsonResponse({'code': 0, 'data': data})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def role_create(request):
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    name = (body.get('role_name') or '').strip()
    code = (body.get('role_code') or '').strip()
    if not name or not code:
        return JsonResponse({'code': 400, 'message': '角色名称与编码不能为空'}, status=400)
    if ZRole.objects.filter(role_code=code).exists():
        return JsonResponse({'code': 400, 'message': '角色编码已存在'}, status=400)
    menu_ids = body.get('menu_ids')
    if menu_ids is not None and not isinstance(menu_ids, list):
        return JsonResponse({'code': 400, 'message': 'menu_ids 须为数组'}, status=400)
    with transaction.atomic():
        r = ZRole.objects.create(
            role_name=name,
            role_code=code,
            remark=(body.get('remark') or '').strip(),
            status=int(body.get('status') if body.get('status') is not None else 1),
        )
        if menu_ids is not None:
            _set_role_menus(r, menu_ids)
    return JsonResponse({'code': 0, 'message': '创建成功', 'data': _serialize_role(r)})


@csrf_exempt
@require_http_methods(['PUT', 'PATCH'])
@require_valid_token
def role_update(request, pk):
    try:
        r = ZRole.objects.get(pk=pk)
    except ZRole.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '角色不存在'}, status=404)
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    if 'role_name' in body:
        r.role_name = (body.get('role_name') or '').strip()
    if 'role_code' in body:
        c = (body.get('role_code') or '').strip()
        if c and ZRole.objects.exclude(pk=r.pk).filter(role_code=c).exists():
            return JsonResponse({'code': 400, 'message': '角色编码已存在'}, status=400)
        if c:
            r.role_code = c
    if 'remark' in body:
        r.remark = (body.get('remark') or '').strip()
    if 'status' in body:
        r.status = int(body.get('status'))
    r.save()
    if 'menu_ids' in body:
        mids = body.get('menu_ids')
        if not isinstance(mids, list):
            return JsonResponse({'code': 400, 'message': 'menu_ids 须为数组'}, status=400)
        _set_role_menus(r, mids)
    return JsonResponse({'code': 0, 'message': '保存成功', 'data': _serialize_role(r)})


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
@require_valid_token
@require_super_admin
def role_delete(request, pk):
    try:
        r = ZRole.objects.get(pk=pk)
    except ZRole.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '角色不存在'}, status=404)
    if r.role_code == 'super_admin':
        return JsonResponse({'code': 403, 'message': '超级管理员角色不可删除'}, status=403)
    from apps.users.models import ZUser
    if ZUser.objects.filter(role_id=pk).exists():
        return JsonResponse({'code': 400, 'message': '仍有用户绑定该角色，无法删除'}, status=400)
    r.delete()
    return JsonResponse({'code': 0, 'message': '已删除'})
