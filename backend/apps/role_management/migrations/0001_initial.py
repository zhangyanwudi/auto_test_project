import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('menu_management', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ZRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role_name', models.CharField(max_length=128, verbose_name='角色名称')),
                ('role_code', models.CharField(db_index=True, max_length=64, unique=True, verbose_name='角色编码')),
                ('remark', models.CharField(blank=True, default='', max_length=255, verbose_name='备注')),
                ('status', models.SmallIntegerField(default=1, help_text='1-启用 0-停用', verbose_name='状态')),
                ('create_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('update_time', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '角色',
                'verbose_name_plural': '角色',
                'db_table': 'z_role',
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='ZRoleMenu',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('menu', models.ForeignKey(db_column='menu_id', on_delete=django.db.models.deletion.CASCADE, related_name='role_menus', to='menu_management.zmenu')),
                ('role', models.ForeignKey(db_column='role_id', on_delete=django.db.models.deletion.CASCADE, related_name='role_menus', to='role_management.zrole')),
            ],
            options={
                'verbose_name': '角色菜单',
                'db_table': 'z_role_menu',
                'unique_together': {('role', 'menu')},
            },
        ),
    ]
