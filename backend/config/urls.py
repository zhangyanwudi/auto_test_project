"""
URL configuration for auto_test_project backend.
"""
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include


def frontend_login_url(request):
    """按访问后端的 host 拼出前端登录页地址（端口与 FRONTEND_URL 一致）。"""
    parsed = urlparse(settings.FRONTEND_URL.rstrip('/') + '/')
    port = parsed.port or 5173
    scheme = parsed.scheme or 'http'
    host = (request.get_host() or '').split(':')[0]
    if host in ('', '0.0.0.0'):
        host = getattr(settings, 'LOCAL_IP', None) or '127.0.0.1'
    return f'{scheme}://{host}:{port}/'


def vue_app(request):
    """Vue 主页面：重定向到前端登录页（开发时为 Vite 开发服务器）。"""
    return redirect(frontend_login_url(request))


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('apis.urls')),
    path('', vue_app),
]
