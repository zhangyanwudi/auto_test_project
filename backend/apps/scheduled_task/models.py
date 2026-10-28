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
    is_running = models.BooleanField('是否运行中', default=False)
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


class ZScheduledTaskRunLog(models.Model):
    """定时任务执行日志：每次执行（立即运行 / Cron 调度）落一条，供页面展示执行历史与详情。"""

    TRIGGER_MANUAL = 'manual'
    TRIGGER_CRON = 'cron'
    TRIGGER_CHOICES = (
        (TRIGGER_MANUAL, '立即运行'),
        (TRIGGER_CRON, '定时调度'),
    )

    task_id = models.BigIntegerField('任务ID', db_index=True)
    trigger_type = models.CharField('触发方式', max_length=16, default=TRIGGER_MANUAL)
    start_time = models.DateTimeField('开始执行时间')
    end_time = models.DateTimeField('结束执行时间', null=True, blank=True)
    duration_ms = models.IntegerField('执行时长（毫秒）', default=0)
    success = models.BooleanField('是否成功', default=False)
    message = models.CharField('执行说明', max_length=512, blank=True, default='')
    detail_json = models.TextField('执行详情JSON', blank=True, default='')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        app_label = 'scheduled_task'
        db_table = 'z_scheduled_task_run_log'
        verbose_name = '定时任务执行日志'
        verbose_name_plural = '定时任务执行日志'
        ordering = ['-id']

    def __str__(self):
        return f'{self.task_id}@{self.start_time}'
