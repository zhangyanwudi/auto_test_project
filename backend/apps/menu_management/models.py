from django.db import models


class ZMenu(models.Model):
    """后台菜单表 z_menu：名称、编码、路由、父级、图标、排序、状态"""
    menu_name = models.CharField('菜单名称', max_length=128)
    menu_code = models.CharField('菜单编码', max_length=64, unique=True, db_index=True)
    path = models.CharField('前端路径', max_length=255, blank=True, default='',
                            help_text='如 /home 或与 menu_code 对应的前端标识')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父菜单',
    )
    icon = models.CharField('图标', max_length=64, blank=True, default='')
    sort_order = models.PositiveIntegerField('排序', default=0)
    status = models.SmallIntegerField('状态', default=1, help_text='1-启用 0-停用')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'menu_management'
        db_table = 'z_menu'
        verbose_name = '菜单'
        verbose_name_plural = '菜单'
        # 排序字段从小到大；同值时按 id
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.menu_name
