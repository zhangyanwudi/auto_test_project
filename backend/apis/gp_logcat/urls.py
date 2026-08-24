from django.urls import path
from . import views

urlpatterns = [
    path('ingest/', views.gp_logcat_ingest),
    path('stream/', views.gp_logcat_stream),
    path('status/', views.gp_logcat_status),
    path('clear/', views.gp_logcat_clear),
    path('start/', views.gp_logcat_start),
    path('stop/', views.gp_logcat_stop),
    path('agent/', views.gp_logcat_agent_script),
    path('agent/bootstrap/', views.gp_logcat_agent_bootstrap),
]
