from django.urls import path
from . import views

urlpatterns = [
    path('menus/', views.menu_list),
    path('menus/create/', views.menu_create),
    path('menus/<int:pk>/', views.menu_update),
    path('menus/<int:pk>/status/', views.menu_status),
    path('menus/<int:pk>/delete/', views.menu_delete),
]
