from django.db import models


class ZDbTableNote(models.Model):
    """数据库表备注 z_db_table_note：记录某连接下某张表的备注与相关执行 SQL。"""

    connection_id = models.CharField('连接配置标识', max_length=64)
    table_name = models.CharField('表名', max_length=192)
    note = models.TextField('表备注', null=True, blank=True, default='')
    sql_records = models.TextField('相关执行 SQL', null=True, blank=True, default='',
                                   help_text='多条 SQL 用换行分隔')
    field_notes = models.TextField('字段手动备注', null=True, blank=True, default='',
                                   help_text='字段手动备注，JSON：{"字段名":"备注"}')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'db_table_note'
        db_table = 'z_db_table_note'
        verbose_name = '数据库表备注'
        verbose_name_plural = '数据库表备注'
        unique_together = [['connection_id', 'table_name']]
        ordering = ['-id']

    def __str__(self):
        return '%s/%s' % (self.connection_id, self.table_name)


class ZDbTableNoteConnection(models.Model):
    """数据库连接配置 z_db_table_note_connection：存储连接信息，避免部署时被覆盖丢失。"""

    connection_id = models.CharField('连接配置标识', max_length=64, unique=True, db_index=True)
    name = models.CharField('显示名称', max_length=128, blank=True, default='')
    host = models.CharField('地址', max_length=255)
    port = models.IntegerField('端口', default=3306)
    user = models.CharField('用户名', max_length=128)
    password = models.CharField('密码', max_length=255)
    database = models.CharField('数据库名', max_length=128)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'db_table_note'
        db_table = 'z_db_table_note_connection'
        verbose_name = '数据库连接配置'
        verbose_name_plural = '数据库连接配置'
        ordering = ['id']

    def __str__(self):
        return '%s(%s)' % (self.name or self.connection_id, self.connection_id)
