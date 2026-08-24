from django.urls import path
from . import views

urlpatterns = [
    # —— 规则管理 CRUD ——
    path('rules/', views.mock_rule_list),
    path('rules/create/', views.mock_rule_create),
    path('rules/<int:pk>/', views.mock_rule_update),
    path('rules/<int:pk>/status/', views.mock_rule_status),
    path('rules/<int:pk>/delete/', views.mock_rule_delete),

    # —— 代理启停 ——
    path('proxy/start/', views.mock_proxy_start),
    path('proxy/stop/', views.mock_proxy_stop),
    path('proxy/status/', views.mock_proxy_status),
    path('proxy/reload/', views.mock_proxy_reload),

    # —— 数据库连接配置 ——
    path('db_configs/', views.mock_db_config_list),
    path('db_configs/create/', views.mock_db_config_create),
    path('db_configs/<int:pk>/', views.mock_db_config_update),
    path('db_configs/<int:pk>/delete/', views.mock_db_config_delete),

    # —— 规则测试 ——
    path('rules/test_match/', views.mock_rule_test_match),
]
