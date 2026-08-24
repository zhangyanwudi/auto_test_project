from django.urls import path
from . import views

urlpatterns = [
    path('roles/', views.role_list),
    path('roles/create/', views.role_create),
    path('roles/<int:pk>/', views.role_update),
    path('roles/<int:pk>/delete/', views.role_delete),
    path('menus/options/', views.menu_options),
]
