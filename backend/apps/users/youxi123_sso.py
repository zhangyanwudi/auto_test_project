"""
youxi123 统一 SSO（ticket 验证型）客户端封装。

流程：
1. build_login_url() 生成 youxi123 登录页 URL（带 next 回调参数），前端跳转
2. 用户登录后 SSO 跳回 callback_url?ticket=xxx
3. verify_ticket(ticket) 用 ticket 换取用户信息（username/full_name/email 等）

对接参数参考：/Users/admin/Desktop/ZnYan/zt_onetest/backend/autotest/services/system/sso.py
"""
import json
from urllib.parse import urlencode

import requests
from django.conf import settings


class Youxi123SsoError(Exception):
    """youxi123 SSO 登录过程中的业务异常。"""


def _config():
    return getattr(settings, 'YOUXI123_SSO_CONFIG', None) or {}


def is_configured():
    """是否已填写 SSO 必要配置（login_url/verify_url/secret_key）。"""
    cfg = _config()
    return bool(
        (cfg.get('login_url') or '').strip()
        and (cfg.get('verify_url') or '').strip()
        and (cfg.get('secret_key') or '').strip()
    )


def build_login_url(callback_url=None):
    """拼装 youxi123 登录页 URL，next 指向后端回调地址（未显式传入时用配置里的）。"""
    cfg = _config()
    login_url = (cfg.get('login_url') or '').strip()
    callback = (callback_url or cfg.get('callback_url') or '').strip()
    next_param = urlencode({'next': callback})
    return f'{login_url}?{next_param}'


def verify_ticket(ticket):
    """用 SSO ticket 换取用户信息。返回用户信息 dict（含 username/full_name/email 等）。"""
    cfg = _config()
    verify_url = (cfg.get('verify_url') or '').strip()
    payload = {
        'ticket': ticket,
        'secret_key': (cfg.get('secret_key') or '').strip(),
    }
    try:
        resp = requests.post(
            verify_url,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'},
            timeout=10,
        )
    except requests.RequestException as e:
        raise Youxi123SsoError(f'SSO 验证请求异常：{e}')

    if resp.status_code != 200:
        raise Youxi123SsoError(f'SSO 验证失败：HTTP {resp.status_code}')

    try:
        data = resp.json()
    except json.JSONDecodeError:
        raise Youxi123SsoError('SSO 验证返回格式错误')

    # 兼容两种返回结构：直接用户信息 dict，或 {..., "data": {...}}
    if isinstance(data, dict) and isinstance(data.get('data'), dict):
        data = data['data']
    if not isinstance(data, dict):
        raise Youxi123SsoError('SSO 验证返回数据异常')
    return data
