import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from apps.users.models import ZUser
from apps.users.decorators import require_valid_token, require_super_admin
from apps.role_management.models import ZRole

try:
    from base_utils.secrecy_base import md5_en
except ImportError:
    def md5_en(s):
        return s


def _admin_user_id():
    """第一条用户（id 最小）为管理员，不可删除"""
    agg = ZUser.objects.order_by('id').values_list('id', flat=True).first()
    return agg


def _role_label(role_id):
    if not role_id:
        return None, ''
    try:
        r = ZRole.objects.get(pk=role_id)
        return r.id, r.role_name
    except ZRole.DoesNotExist:
        return role_id, ''


def _serialize_user(u):
    rid = getattr(u, 'role_id', None)
    _, role_name = _role_label(rid) if rid else (None, '')
    return {
        'id': u.id,
        'user_name': u.user_name,
        'user_cn_name': getattr(u, 'user_cn_name', '') or '',
        'user_status': u.user_status,
        'user_power': u.user_power,
        'role_id': rid,
        'role_name': role_name or None,
        'create_time': u.create_time.isoformat() if u.create_time else None,
        'login_time': u.login_time.isoformat() if u.login_time else None,
    }


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def user_list(request):
    """z_user 用户列表，按 id 排序，第一条为管理员"""
    qs = ZUser.objects.all().order_by('id')
    admin_id = _admin_user_id()
    data = []
    for u in qs:
        row = _serialize_user(u)
        row['is_admin'] = u.id == admin_id
        data.append(row)
    return JsonResponse({'code': 0, 'data': data})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def user_create(request):
    """新增用户"""
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    user_name = (body.get('user_name') or '').strip()
    password = body.get('password') or ''
    user_cn_name = (body.get('user_cn_name') or '').strip() or user_name
    if not user_name:
        return JsonResponse({'code': 400, 'message': '请输入用户名'}, status=400)
    if not password:
        return JsonResponse({'code': 400, 'message': '请输入密码'}, status=400)
    if ZUser.objects.filter(user_name=user_name).exists():
        return JsonResponse({'code': 400, 'message': '用户名已存在'}, status=400)
    now = timezone.now()
    role_id = body.get('role_id')
    if role_id is not None and role_id != '':
        try:
            ZRole.objects.get(pk=int(role_id))
        except (ZRole.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'code': 400, 'message': '角色不存在'}, status=400)
    u = ZUser.objects.create(
        user_name=user_name,
        user_cn_name=user_cn_name,
        user_password=md5_en(password),
        user_token='',
        user_status=int(body.get('user_status') if body.get('user_status') is not None else 1),
        user_power=int(body.get('user_power') or 0),
        role_id=int(role_id) if role_id not in (None, '') else None,
        create_time=now,
        login_time=now,
    )
    return JsonResponse({'code': 0, 'message': '创建成功', 'data': _serialize_user(u)})


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
@require_valid_token
@require_super_admin
def user_delete(request, pk):
    """删除用户（管理员第一条不可删）"""
    admin_id = _admin_user_id()
    if int(pk) == admin_id:
        return JsonResponse({'code': 403, 'message': '管理员用户不可删除'}, status=403)
    try:
        u = ZUser.objects.get(pk=pk)
    except ZUser.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用户不存在'}, status=404)
    u.delete()
    return JsonResponse({'code': 0, 'message': '已删除'})


@csrf_exempt
@require_http_methods(['POST', 'PUT'])
@require_valid_token
def user_change_password(request, pk):
    """修改密码"""
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    new_password = body.get('new_password') or body.get('password') or ''
    if not new_password:
        return JsonResponse({'code': 400, 'message': '请输入新密码'}, status=400)
    try:
        u = ZUser.objects.get(pk=pk)
    except ZUser.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用户不存在'}, status=404)
    u.user_password = md5_en(new_password)
    u.user_token = ''  # 改密后清除 token，需重新登录
    u.save(update_fields=['user_password', 'user_token'])
    return JsonResponse({'code': 0, 'message': '密码已更新'})


@csrf_exempt
@require_http_methods(['PUT', 'PATCH'])
@require_valid_token
def user_update(request, pk):
    """编辑用户（中文名、状态等，不含密码）"""
    try:
        u = ZUser.objects.get(pk=pk)
    except ZUser.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用户不存在'}, status=404)
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    if 'user_cn_name' in body:
        u.user_cn_name = (body.get('user_cn_name') or '').strip() or u.user_name
    if 'user_status' in body:
        admin_id = _admin_user_id()
        if u.id == admin_id and int(body.get('user_status')) != 1:
            return JsonResponse({'code': 403, 'message': '不可停用管理员账号'}, status=403)
        u.user_status = int(body.get('user_status'))
    if 'user_power' in body:
        u.user_power = int(body.get('user_power') or 0)
    if 'role_id' in body:
        rid = body.get('role_id')
        if rid in (None, ''):
            u.role_id = None
        else:
            try:
                ZRole.objects.get(pk=int(rid))
                u.role_id = int(rid)
            except (ZRole.DoesNotExist, ValueError, TypeError):
                return JsonResponse({'code': 400, 'message': '角色不存在'}, status=400)
    u.save()
    return JsonResponse({'code': 0, 'message': '保存成功', 'data': _serialize_user(u)})
