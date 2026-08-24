from django.db import models


class ZScheduledTask(models.Model):
    """
    定时任务配置：使用标准 5 段 crontab（分 时 日 月 周），与业务执行器解耦，仅作配置存储。
    """

    task_name = models.CharField('任务名称', max_length=128)
    task_code = models.CharField('任务编码', max_length=64, unique=True, db_index=True)
    description = models.CharField('说明', max_length=512, blank=True, default='')
    # 例如 "30 9 * * *" 表示每天 9:30
    cron_expression = models.CharField('Cron 表达式', max_length=128)
    # file：从 task_file 目录选择脚本；other：不绑定目录内文件
    execution_type = models.CharField(
        '执行类型', max_length=32, default='file', db_index=True
    )
    task_file_name = models.CharField(
        '执行文件名', max_length=256, blank=True, default='',
        help_text='相对于 backend/task_file 目录下的文件名',
    )
    status = models.SmallIntegerField('状态', default=1, help_text='1-启用 0-停用')
    last_run_time = models.DateTimeField('最近执行', null=True, blank=True)
    last_run_success = models.BooleanField('最近执行是否成功', null=True, blank=True)
    last_run_message = models.CharField('最近执行说明', max_length=512, blank=True, default='')
    last_run_detail = models.TextField('最近执行详情JSON', blank=True, default='')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'scheduled_task'
        db_table = 'z_scheduled_task'
        verbose_name = '定时任务'
        verbose_name_plural = '定时任务'
        ordering = ['-id']

    def __str__(self):
        return self.task_name
