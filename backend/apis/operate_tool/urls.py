from django.urls import path

from . import git_config_views

urlpatterns = [
    path('git_config_diff/get_git_info/', git_config_views.get_git_info),
    path('git_config_diff/get_adwaynum_file/', git_config_views.get_adwaynum_file),
    path('git_config_diff/get_adwaynum_json_2/', git_config_views.get_adwaynum_json_2),
    path('git_config_diff/report_statistic_info/', git_config_views.report_statistic_info),
    path('git_config_diff/rebuild_adwaynum_cache/', git_config_views.rebuild_adwaynum_cache),
]
