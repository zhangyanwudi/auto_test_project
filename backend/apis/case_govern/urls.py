from django.urls import path
from . import views

urlpatterns = [
    path('modules/', views.module_list),
    path('cases/', views.case_list),
    path('cases/create/', views.case_create),
    path('cases/import/', views.case_import),
    path('cases/import_emmx/', views.case_import_emmx),
    path('cases/<int:pk>/mind/', views.case_mind),
    path('cases/<int:pk>/mind/save/', views.case_mind_save),
    path('cases/<int:pk>/delete/', views.case_delete),
    path('cases/<int:pk>/', views.case_update),
]
