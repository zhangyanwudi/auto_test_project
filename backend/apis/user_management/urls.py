from django.urls import path
from . import views

urlpatterns = [
    path('users/', views.user_list),
    path('users/create/', views.user_create),
    path('users/<int:pk>/delete/', views.user_delete),
    path('users/<int:pk>/password/', views.user_change_password),
    path('users/<int:pk>/', views.user_update),
]
