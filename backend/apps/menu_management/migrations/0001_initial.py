# Generated manually for z_menu

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ZMenu',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('menu_name', models.CharField(max_length=128, verbose_name='菜单名称')),
                ('menu_code', models.CharField(db_index=True, max_length=64, unique=True, verbose_name='菜单编码')),
                ('path', models.CharField(blank=True, default='', help_text='如 /home 或与 menu_code 对应的前端标识', max_length=255, verbose_name='前端路径')),
                ('icon', models.CharField(blank=True, default='', max_length=64, verbose_name='图标')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='排序')),
                ('status', models.SmallIntegerField(default=1, help_text='1-启用 0-停用', verbose_name='状态')),
                ('create_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('update_time', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='menu_management.zmenu', verbose_name='父菜单')),
            ],
            options={
                'verbose_name': '菜单',
                'verbose_name_plural': '菜单',
                'db_table': 'z_menu',
                'ordering': ['sort_order', 'id'],
            },
        ),
    ]
