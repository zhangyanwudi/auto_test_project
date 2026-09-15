from django.db import models


class ZConfigCompareStat(models.Model):
    """配置比对使用统计：每次比对操作记录一条"""

    project_names = models.CharField('项目名称', max_length=1024, default='')
    user_name = models.CharField('操作人', max_length=255, default='')
    compare_type = models.CharField(
        '比对类型', max_length=32, default='single',
        help_text='single-单次对比 batch-批量比对'
    )
    left_Adwaynum = models.CharField('左侧方案', max_length=512, default='')
    right_Adwaynum = models.CharField('右侧方案', max_length=512, default='')
    leftTimeslot = models.CharField('左侧时间段', max_length=64, default='')
    rightTimeslot = models.CharField('右侧时间段', max_length=64, default='')
    left_region = models.CharField('左侧区域', max_length=255, default='')
    right_region = models.CharField('右侧区域', max_length=255, default='')
    batch_left_count = models.IntegerField('批量-左侧方案数', default=0)
    batch_right_count = models.IntegerField('批量-右侧方案数', default=0)
    batch_pair_count = models.IntegerField('批量-配对数', default=0)
    raw_data = models.TextField('原始上报数据', blank=True, default='')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        app_label = 'operate_tool'
        db_table = 'z_config_compare_stat'
        verbose_name = '配置比对统计'
        verbose_name_plural = '配置比对统计'
        ordering = ['-id']

    def __str__(self):
        return f'{self.user_name} - {self.compare_type} - {self.create_time}'


class ZFeatureUsage(models.Model):
    """功能使用记录：用户进入某功能页停留满 1 分钟计一次使用。"""

    menu_code = models.CharField('功能编码', max_length=64)
    menu_name = models.CharField('功能名称', max_length=128)
    user_name = models.CharField('使用人', max_length=255)
    create_time = models.DateTimeField('上报时间', auto_now_add=True)

    class Meta:
        app_label = 'operate_tool'
        db_table = 'z_feature_usage'
        verbose_name = '功能使用记录'
        verbose_name_plural = '功能使用记录'
        ordering = ['-id']
        indexes = [
            models.Index(fields=['menu_code', 'create_time'], name='idx_menu_time'),
            models.Index(fields=['create_time'], name='idx_feature_create_time'),
        ]

    def __str__(self):
        return f'{self.menu_code} - {self.user_name} - {self.create_time}'
