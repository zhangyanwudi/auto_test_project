"""
登录相关 API：供登录页使用的接口
"""
import json
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from apps.users import youxi123_sso
from apps.users.models import ZUser
from apps.users.login_token import generate_token, get_expires_at
from apps.users.role_utils import get_user_role_flags
from apps.role_management.models import ZRole
from base_utils.config_base import load_page_config

try:
    from base_utils.secrecy_base import md5_en
except ImportError:
    def md5_en(s):
        return s


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    """
    登录接口：校验用户是否存在且密码正确。
    请求体: { "username": "xxx", "password": "xxx" }
    成功：更新 user_token、login_time，返回 token 与过期时间；
    失败：返回 401 及错误信息。
    """
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    username = (body.get('username') or '').strip()
    raw_password = body.get('password') or ''
    password = md5_en(raw_password)
    if not username:
        return JsonResponse({'code': 400, 'message': '请输入用户名'}, status=400)
    if not password:
        return JsonResponse({'code': 400, 'message': '请输入密码'}, status=400)

    user = ZUser.get_by_username(username)
    if user is None:
        return JsonResponse({'code': 401, 'message': '用户不存在'}, status=401)
    if user.user_status != 1:
        return JsonResponse({'code': 401, 'message': '账号已停用'}, status=401)
    if user.user_password != password:
        return JsonResponse({'code': 401, 'message': '密码错误'}, status=401)

    data = _issue_token(user)
    return JsonResponse({'code': 0, 'message': '登录成功', 'data': data})


def _issue_token(user):
    """为已通过校验的用户签发新 token（更新 login_time），返回登录成功 data。"""
    now = timezone.now()
    user.user_token = generate_token()
    user.login_time = now
    user.save(update_fields=['user_token', 'login_time'])

    expires_at = get_expires_at(now)
    cn_name = (getattr(user, 'user_cn_name', None) or '').strip() or user.user_name
    flags = get_user_role_flags(user)
    return {
        'token': user.user_token,
        'expires_at': expires_at.isoformat() if expires_at else None,
        'username': user.user_name,
        'user_cn_name': cn_name,
        'role_code': flags['role_code'],
        'is_super_admin': flags['is_super_admin'],
    }


def _page_config():
    """读取 page_config.json 内容。"""
    return load_page_config()


def _sso_enabled():
    """统一 SSO 登录开关是否开启。"""
    return bool(_page_config().get('sso_enabled', False))


# 统一 SSO 首次登录自动分配的角色（与数据库 z_role 中「普通用户」角色编码 general_user 保持一致）
SSO_DEFAULT_ROLE_CODE = 'general_user'
SSO_DEFAULT_ROLE_NAME = '普通用户'


def _get_or_create_normal_role():
    """获取或创建「普通用户」角色，用于统一 SSO 首次登录自动分配。"""
    try:
        role, _ = ZRole.objects.get_or_create(
            role_code=SSO_DEFAULT_ROLE_CODE,
            defaults={
                'role_name': SSO_DEFAULT_ROLE_NAME,
                'remark': '统一SSO首次登录自动分配',
                'status': 1,
            },
        )
        return role
    except Exception:
        return None


def _client_host(request):
    """客户端访问后端的主机（IP/域名）；仅空或 0.0.0.0 时回退到本机局域网 IP。

    直接跟随当前访问地址：本机调试访问 localhost 就是 localhost，部署后访问服务器 IP 就是服务器 IP。
    """
    host = (request.get_host() or '').split(':')[0]
    if host in ('', '0.0.0.0'):
        host = getattr(settings, 'LOCAL_IP', None) or '127.0.0.1'
    return host


def _frontend_base(request):
    """前端基础地址：客户端访问的本机 IP + FRONTEND_URL 的端口与协议。"""
    parsed = urlparse(settings.FRONTEND_URL.rstrip('/') + '/')
    port = parsed.port or 5173
    scheme = parsed.scheme or 'http'
    return f'{scheme}://{_client_host(request)}:{port}'


def _get_or_create_sso_user(info):
    """根据 SSO 用户信息匹配或创建本地用户，返回 (user, error_msg)。"""
    username = (info.get('username') or '').strip()
    if not username:
        email = (info.get('email') or '').strip()
        username = email.split('@')[0].strip()
    if not username:
        return None, 'SSO 未返回用户名'

    full_name = (info.get('full_name') or '').strip() or username

    user = ZUser.get_by_username(username)
    if user is None:
        now = timezone.now()
        role = _get_or_create_normal_role()
        user = ZUser.objects.create(
            user_name=username,
            user_cn_name=full_name,
            user_password='',
            user_token='',
            user_status=1,
            user_power=0,
            role_id=role.id if role else None,
            create_time=now,
            login_time=now,
        )
    if user.user_status != 1:
        return None, '账号已停用'
    return user, None


@csrf_exempt
@require_http_methods(["GET"])
def youxi123_login_url(request):
    """返回 youxi123 统一 SSO 登录地址（next 指向前端，登录后 ticket 回到前端），前端拿到后跳转。"""
    if not _sso_enabled():
        return JsonResponse({'code': 403, 'message': '统一登录未开启'}, status=403)
    if not youxi123_sso.is_configured():
        return JsonResponse({'code': 400, 'message': '统一登录未配置，请在 config/page_config.json 的 youxi123_sso 分组填写 login_url/verify_url/secret_key'}, status=400)
    frontend_url = _frontend_base(request) + '/home'
    return JsonResponse({'code': 0, 'data': {'login_url': youxi123_sso.build_login_url(frontend_url)}})


@csrf_exempt
@require_http_methods(["POST"])
def youxi123_verify_ticket(request):
    """验证 SSO ticket，签发本地 token（前端拿到 SSO 回调 ticket 后调用）。"""
    if not _sso_enabled():
        return JsonResponse({'code': 403, 'message': '统一登录未开启'}, status=403)
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    ticket = (body.get('ticket') or '').strip()
    if not ticket:
        return JsonResponse({'code': 400, 'message': '缺少 SSO ticket'}, status=400)

    try:
        info = youxi123_sso.verify_ticket(ticket)
    except youxi123_sso.Youxi123SsoError as e:
        return JsonResponse({'code': 401, 'message': str(e)}, status=401)
    except Exception as e:  # noqa: BLE001
        return JsonResponse({'code': 500, 'message': f'统一登录失败：{e}'}, status=500)

    user, err = _get_or_create_sso_user(info)
    if err:
        return JsonResponse({'code': 401, 'message': err}, status=401)

    data = _issue_token(user)
    return JsonResponse({'code': 0, 'message': '登录成功', 'data': data})
