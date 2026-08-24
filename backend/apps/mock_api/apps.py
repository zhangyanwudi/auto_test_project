from django.apps import AppConfig


class MockApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mock_api'
    verbose_name = 'Mock接口管理'
