"""
Token 生成与过期校验（与 z_user 表 login_time 配合，过期时间默认 7 天）
"""
import secrets
from datetime import timedelta
from django.utils import timezone


# 默认 token 有效天数
DEFAULT_EXPIRE_DAYS = 7


def generate_token():
    """生成随机 token 字符串，用于写入 z_user.user_token。"""
    return secrets.token_hex(32)


def is_token_expired(login_time, expire_days=DEFAULT_EXPIRE_DAYS):
    """
    根据登录时间判断 token 是否已过期。

    :param login_time: 登录时间（datetime，若为 None 视为已过期）
    :param expire_days: 有效天数，默认 7 天
    :return: True 表示已过期，False 表示未过期
    """
    if login_time is None:
        return True
    now = timezone.now()
    if timezone.is_naive(login_time):
        login_time = timezone.make_aware(login_time)
    expiry = login_time + timedelta(days=expire_days)
    return now >= expiry


def get_expires_at(login_time, expire_days=DEFAULT_EXPIRE_DAYS):
    """根据登录时间计算 token 过期时间点（用于返回给前端）。"""
    if login_time is None:
        return None
    if timezone.is_naive(login_time):
        login_time = timezone.make_aware(login_time)
    return login_time + timedelta(days=expire_days)
