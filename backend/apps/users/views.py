from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import ZUser


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
    from .login_token import get_expires_at
    expires_at = get_expires_at(user.login_time)
    return JsonResponse({
        'code': 0,
        'data': {
            'username': user.user_name,
            'expires_at': expires_at.isoformat() if expires_at else None,
        },
    })
