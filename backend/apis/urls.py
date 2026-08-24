"""
apis 主路由：按功能拆分到子目录，公共 API 在 common，各页面/模块 API 在对应目录。
"""
from django.urls import path, include

urlpatterns = [
    path('operate_tool/', include('apis.operate_tool.urls')),
    path('ocr/', include('apis.ocr.urls')),
    path('common/', include('apis.common.urls')),
    path('login/', include('apis.login.urls')),
    path('menu_management/', include('apis.menu_management.urls')),
    path('user_management/', include('apis.user_management.urls')),
    path('role_management/', include('apis.role_management.urls')),
    path('scheduled_task/', include('apis.scheduled_task.urls')),
    path('ai_helper/', include('apis.ai_helper.urls')),
    path('home/', include('apis.home.urls')),
    path('gp_logcat/', include('apis.gp_logcat.urls')),
    path('mock_api/', include('apis.mock_api.urls')),
    path('case_govern/', include('apis.case_govern.urls')),
    path('llm/', include('apis.llm.urls')),
]
