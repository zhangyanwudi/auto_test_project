from django.apps import AppConfig


class ScheduledTaskConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.scheduled_task'
    verbose_name = '定时任务'
