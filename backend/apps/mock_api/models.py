from django.db import models


class ZMockApiRule(models.Model):
    """Mock API 规则配置表 z_mock_api_rule：URL 模式、匹配方式、响应数据、状态"""
    rule_name = models.CharField('规则名称', max_length=128)
    url_pattern = models.CharField('URL 匹配模式', max_length=512, help_text='拦截的 URL 或关键字')
    match_type = models.CharField(
        '匹配方式',
        max_length=32,
        default='contains',
        choices=[('contains', '包含'), ('regex', '正则'), ('exact', '精确')],
    )
    response_file = models.CharField(
        '响应数据文件',
        max_length=512,
        blank=True,
        default='',
        help_text='JSON 响应数据文件路径（最高优先级）',
    )
    response_data = models.TextField(
        '内联响应数据',
        blank=True,
        default='',
        help_text='直接填入的响应数据，支持 JSON 或非 JSON 格式（纯文本、base64 字符串等），可作为数据库查询降级 fallback',
    )
    response_sql = models.TextField(
        'SQL 查询语句',
        blank=True,
        default='',
        help_text='命中规则时实时执行的 SQL 查询',
    )
    response_db = models.TextField(
        '数据库连接配置',
        blank=True,
        default='',
        help_text='JSON 格式的数据库连接信息: {host, port, username, password, database, db_type}',
    )
    status_code = models.PositiveIntegerField('响应 HTTP 状态码', default=200)
    status = models.SmallIntegerField('状态', default=1, help_text='1-启用 0-停用')
    sort_order = models.PositiveIntegerField('排序', default=0)
    remark = models.CharField('备注', max_length=512, blank=True, default='')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'mock_api'
        db_table = 'z_mock_api_rule'
        verbose_name = 'Mock API 规则'
        verbose_name_plural = 'Mock API 规则'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.rule_name


class ZMockApiDbConfig(models.Model):
    """Mock API 数据库连接配置表 z_mock_api_db_config：可复用的数据库连接"""
    config_key = models.CharField('连接标识', max_length=64, unique=True, db_index=True)
    db_type = models.CharField('数据库类型', max_length=32, default='mysql')
    host = models.CharField('主机地址', max_length=128)
    port = models.PositiveIntegerField('端口', default=3306)
    username = models.CharField('用户名', max_length=64)
    password = models.CharField('密码', max_length=256)
    database = models.CharField('数据库名', max_length=128)
    status = models.SmallIntegerField('状态', default=1, help_text='1-启用 0-停用')
    remark = models.CharField('备注', max_length=512, blank=True, default='')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'mock_api'
        db_table = 'z_mock_api_db_config'
        verbose_name = 'Mock API 数据库配置'
        verbose_name_plural = 'Mock API 数据库配置'
        ordering = ['id']

    def __str__(self):
        return f'{self.config_key} ({self.db_type}://{self.host}:{self.port}/{self.database})'
