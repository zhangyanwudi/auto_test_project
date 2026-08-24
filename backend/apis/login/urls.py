from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login),
    path('youxi123/login_url/', views.youxi123_login_url),
    path('youxi123/verify_ticket/', views.youxi123_verify_ticket),
]
