from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health),
    path('token_check/', views.token_check),
    path('page_config/', views.get_page_config),
]
