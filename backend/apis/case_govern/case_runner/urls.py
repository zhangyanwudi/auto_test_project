from django.urls import path
from . import views

urlpatterns = [
    # 阶段一：生成规范 + 试运行
    path('explore/', views.case_explore),
    # 阶段二：用户确认后固化为用例
    path('solidify/', views.case_solidify),
]
