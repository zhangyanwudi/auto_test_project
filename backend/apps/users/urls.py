from django.urls import path
from . import views

urlpatterns = [
    path('token_check/', views.token_check),
]
