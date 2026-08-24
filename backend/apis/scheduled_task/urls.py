from django.urls import path
from . import views

urlpatterns = [
    path('task_files/', views.task_file_names),
    path('tasks/', views.task_list),
    path('tasks/create/', views.task_create),
    path('tasks/<int:pk>/run/', views.task_run_now),
    path('tasks/<int:pk>/status/', views.task_status),
    path('tasks/<int:pk>/delete/', views.task_delete),
    path('tasks/<int:pk>/', views.task_update),
]
