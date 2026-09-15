from django.urls import path

from . import views

urlpatterns = [
    path('daily_statistic/', views.get_daily_statistic),
    path('feature_usage/report/', views.feature_usage_report),
    path('feature_usage/statistic/', views.feature_usage_statistic),
]
