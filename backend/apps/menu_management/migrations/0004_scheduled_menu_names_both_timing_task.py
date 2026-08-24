"""侧栏层级【定时任务】-【定时任务】：分组与子菜单展示名均为「定时任务」。"""

from django.db import migrations


def forwards(apps, schema_editor):
    ZMenu = apps.get_model('menu_management', 'ZMenu')
    ZMenu.objects.filter(menu_code='page_scheduled').update(menu_name='定时任务')
    ZMenu.objects.filter(menu_code='scheduled_task').update(menu_name='定时任务')


def backwards(apps, schema_editor):
    ZMenu = apps.get_model('menu_management', 'ZMenu')
    ZMenu.objects.filter(menu_code='page_scheduled').update(menu_name='页面定时任务')
    ZMenu.objects.filter(menu_code='scheduled_task').update(menu_name='定时任务页面实现')


class Migration(migrations.Migration):

    dependencies = [
        ('menu_management', '0003_scheduled_task_menu_name_page_impl'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
