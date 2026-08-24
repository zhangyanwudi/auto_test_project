from django.urls import path
from . import views

urlpatterns = [
    path('conversations/', views.conversation_list),
    path('conversations/create/', views.conversation_create),
    path('conversations/clear-all/', views.conversation_clear_all),
    path('conversations/<str:conversation_code>/delete/', views.conversation_delete),
    path('conversations/<str:conversation_code>/messages/', views.conversation_messages),
    path('conversations/<str:conversation_code>/clear-messages/', views.conversation_clear_messages),
    path('chat/', views.chat),
    path('files/upload/', views.upload_file),
    path('files/compare/', views.compare_files),
    path('models/', views.models_info),
]
