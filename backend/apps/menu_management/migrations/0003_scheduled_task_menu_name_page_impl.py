"""子菜单展示名统一为「定时任务页面实现」（非「定时任务实现」「页面定时任务实现」）。"""

from django.db import migrations


def forwards(apps, schema_editor):
    ZMenu = apps.get_model('menu_management', 'ZMenu')
    ZMenu.objects.filter(
        menu_code='scheduled_task',
        menu_name__in=['定时任务', '定时任务实现', '页面定时任务实现'],
    ).update(menu_name='定时任务页面实现')


def backwards(apps, schema_editor):
    ZMenu = apps.get_model('menu_management', 'ZMenu')
    ZMenu.objects.filter(
        menu_code='scheduled_task', menu_name='定时任务页面实现'
    ).update(menu_name='定时任务实现')


class Migration(migrations.Migration):

    dependencies = [
        ('menu_management', '0002_scheduled_task_under_page_scheduled'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
