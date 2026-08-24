from django.urls import path
from . import views

urlpatterns = [
    # 会话管理
    path('session/new/', views.session_new),
    path('session/list/', views.session_list),
    path('session/<str:session_id>/history/', views.session_history),
    path('session/<str:session_id>/clear/', views.session_clear),
    path('session/<str:session_id>/delete/', views.session_delete),

    # 对话
    path('chat/', views.chat),

    # 文件上传与解析
    path('upload/', views.upload_file),

    # 模型列表
    path('models/', views.model_list),
]
