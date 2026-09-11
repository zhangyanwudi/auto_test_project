from django.urls import path
from . import views

urlpatterns = [
    path('connections/', views.connection_list),
    path('connections/save/', views.connection_save),
    path('connections/delete/', views.connection_delete),
    path('tables/', views.table_list),
    path('fields/', views.table_fields),
    path('note/', views.note_get),
    path('note/save/', views.note_save),
]
