from django.db import models


class ZRole(models.Model):
    """角色表 z_role"""
    role_name = models.CharField('角色名称', max_length=128)
    role_code = models.CharField('角色编码', max_length=64, unique=True, db_index=True)
    remark = models.CharField('备注', max_length=255, blank=True, default='')
    status = models.SmallIntegerField('状态', default=1, help_text='1-启用 0-停用')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'role_management'
        db_table = 'z_role'
        verbose_name = '角色'
        verbose_name_plural = '角色'
        ordering = ['id']


class ZRoleMenu(models.Model):
    """角色与菜单关联 z_role_menu"""
    role = models.ForeignKey(
        ZRole,
        on_delete=models.CASCADE,
        related_name='role_menus',
        db_column='role_id',
    )
    menu = models.ForeignKey(
        'menu_management.ZMenu',
        on_delete=models.CASCADE,
        related_name='role_menus',
        db_column='menu_id',
    )

    class Meta:
        app_label = 'role_management'
        db_table = 'z_role_menu'
        verbose_name = '角色菜单'
        unique_together = [['role', 'menu']]
