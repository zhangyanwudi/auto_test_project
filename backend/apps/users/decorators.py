from functools import wraps
from django.http import JsonResponse
from apps.users.models import ZUser
from apps.users.role_utils import get_user_role_flags


def require_valid_token(view_func):
    """校验 Header: Authorization Bearer token，无效则 401。"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth = request.META.get('HTTP_AUTHORIZATION') or ''
        if not auth.startswith('Bearer '):
            return JsonResponse({'code': 401, 'message': '未授权'}, status=401)
        token = auth[7:].strip()
        user = ZUser.get_valid_user_by_token(token)
        if not user:
            return JsonResponse({'code': 401, 'message': 'token 无效或已过期'}, status=401)
        request.z_user = user
        return view_func(request, *args, **kwargs)
    return wrapper


def require_super_admin(view_func):
    """
    须在 @require_valid_token 之内侧使用（保证 request.z_user 已赋值）。
    系统管理员（z_user id 最小）或角色 super_admin 可访问（见 role_utils.get_user_role_flags）。
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, 'z_user', None)
        if not user:
            return JsonResponse({'code': 401, 'message': '未授权'}, status=401)
        if not get_user_role_flags(user)['is_super_admin']:
            return JsonResponse({'code': 403, 'message': '仅超级管理员角色可执行删除操作'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper
