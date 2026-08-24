from django.db import models


class ZCaseGovernCase(models.Model):
    """用例主表 z_case_govern_case：用例记录概要信息（思维导图节点见 ZCaseGovernCaseNode）。"""

    case_name = models.CharField('用例名称', max_length=128)
    module = models.CharField('所属模块', max_length=128, blank=True, default='')
    priority = models.SmallIntegerField('优先级', default=2, help_text='1-高 2-中 3-低')
    status = models.SmallIntegerField('状态', default=1, help_text='1-启用 0-停用')
    creator = models.CharField('创建人', max_length=64, blank=True, default='', help_text='登录用户')
    description = models.CharField('说明', max_length=512, blank=True, default='')
    image = models.TextField('图片', null=True, blank=True, default='', help_text='粘贴的图片（base64 data URL）')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'case_govern'
        db_table = 'z_case_govern_case'
        verbose_name = '用例'
        verbose_name_plural = '用例'
        ordering = ['-id']
        # 同一模块下用例名称唯一
        unique_together = [['case_name', 'module']]

    def __str__(self):
        return self.case_name


class ZCaseGovernCaseNode(models.Model):
    """思维导图节点表 z_case_govern_case_node：parent_id 树形关联，保存用例的思维导图结构。"""

    case = models.ForeignKey(
        ZCaseGovernCase,
        on_delete=models.CASCADE,
        related_name='nodes',
        db_column='case_id',
        verbose_name='所属用例',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        db_column='parent_id',
        verbose_name='父节点',
    )
    node_type = models.CharField(
        '节点类型', max_length=32, default='case',
        help_text='module-模块 case-用例 step-步骤 expect-预期 precondition-前置条件',
    )
    is_smoke = models.BooleanField(
        '冒烟测试', default=False,
        help_text='True-冒烟用例，优先执行',
    )
    exec_result = models.CharField(
        '执行结果', max_length=16, default='',
        help_text='pass-通过 fail-不通过 空-未执行',
    )
    title = models.CharField('节点文本', max_length=512)
    image = models.TextField('图片', null=True, blank=True, default='', help_text='粘贴的图片（base64 data URL）')
    sort_order = models.IntegerField('排序', default=0)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'case_govern'
        db_table = 'z_case_govern_case_node'
        verbose_name = '用例节点'
        verbose_name_plural = '用例节点'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title


class ZCaseGovernModule(models.Model):
    """用例模块表 z_case_govern_module：可配置的所属模块，供新建用例下拉选择。"""

    module_name = models.CharField('模块名称', max_length=128, unique=True, db_index=True)
    status = models.SmallIntegerField('状态', default=1, help_text='1-启用 0-停用')
    sort_order = models.IntegerField('排序', default=0)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'case_govern'
        db_table = 'z_case_govern_module'
        verbose_name = '用例模块'
        verbose_name_plural = '用例模块'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.module_name
