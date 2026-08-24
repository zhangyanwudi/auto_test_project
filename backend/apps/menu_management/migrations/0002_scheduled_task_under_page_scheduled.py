"""将「定时任务」菜单挂到顶层「页面定时任务」下，并从系统管理中移出."""

from django.db import migrations


def forwards(apps, schema_editor):
    ZMenu = apps.get_model('menu_management', 'ZMenu')
    ZRole = apps.get_model('role_management', 'ZRole')
    ZRoleMenu = apps.get_model('role_management', 'ZRoleMenu')

    parent = ZMenu.objects.filter(menu_code='page_scheduled').first()
    if not parent:
        parent = ZMenu.objects.create(
            menu_name='页面定时任务',
            menu_code='page_scheduled',
            path='',
            icon='Clock',
            sort_order=24,
            status=1,
            parent_id=None,
        )

    st = ZMenu.objects.filter(menu_code='scheduled_task').first()
    if st:
        st.parent_id = parent.pk
        if st.menu_name in ('定时任务',):
            st.menu_name = '定时任务页面实现'
        st.save()

    # 超级管理员角色补充勾选「页面定时任务」分组，便于侧栏完整展示
    sa = ZRole.objects.filter(role_code='super_admin').first()
    if sa:
        ZRoleMenu.objects.get_or_create(role_id=sa.pk, menu_id=parent.pk)


def backwards(apps, schema_editor):
    ZMenu = apps.get_model('menu_management', 'ZMenu')
    system = ZMenu.objects.filter(menu_code='system').first()
    if system:
        ZMenu.objects.filter(menu_code='scheduled_task').update(parent_id=system.pk)
    page = ZMenu.objects.filter(menu_code='page_scheduled').first()
    if page:
        page.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('menu_management', '0001_initial'),
        ('role_management', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
