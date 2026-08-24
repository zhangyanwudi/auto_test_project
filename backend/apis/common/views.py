"""
公共 API：多页面共用的接口（如 token 校验、健康检查等）
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.users.models import ZUser
from base_utils.config_base import load_page_config
from apps.users.login_token import get_expires_at
from apps.users.role_utils import get_user_role_flags

def health(request):
    """健康检查，用于探活或监控"""
    return JsonResponse({'status': 'ok', 'message': 'Auto Test 后端运行正常'})


@require_http_methods(["GET", "POST"])
def token_check(request):
    """校验 token 是否有效（Header: Authorization: Bearer <token>），过期规则见 login_token。"""
    auth = request.META.get('HTTP_AUTHORIZATION') or ''
    if not auth.startswith('Bearer '):
        return JsonResponse({'code': 401, 'message': '未提供 token 或 token 已过期'}, status=401)
    token = auth[7:].strip()
    user = ZUser.get_valid_user_by_token(token)
    if not user:
        return JsonResponse({'code': 401, 'message': 'token 无效或已过期'}, status=401)
    expires_at = get_expires_at(user.login_time)
    cn_name = (getattr(user, 'user_cn_name', None) or '').strip() or user.user_name
    flags = get_user_role_flags(user)
    return JsonResponse({
        'code': 0,
        'data': {
            'username': user.user_name,
            'user_cn_name': cn_name,
            'expires_at': expires_at.isoformat() if expires_at else None,
            'role_code': flags['role_code'],
            'is_super_admin': flags['is_super_admin'],
        },
    })


def get_page_config(request):
    """返回 page_config.json 中的非敏感字段（公开接口，敏感信息不对外）。"""
    config = load_page_config()
    return JsonResponse({
        'code': 0,
        'data': {
            'page_tile_name': config.get('page_tile_name', ''),
            'sso_enabled': bool(config.get('sso_enabled', False)),
        },
    })
