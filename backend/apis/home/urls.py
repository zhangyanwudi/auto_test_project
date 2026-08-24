from django.urls import path

from . import views

urlpatterns = [
    path('daily_statistic/', views.get_daily_statistic),
]
