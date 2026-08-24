from django.db import models


class ZUser(models.Model):
    """
    对应现有表 z_user 结构：
    id, user_name, user_password, user_token, user_status, user_power, create_time, login_time
    """
    user_name = models.CharField('用户名', max_length=255, db_column='user_name')
    user_cn_name = models.CharField('中文用户名', max_length=255, db_column='user_cn_name')
    user_password = models.CharField('密码', max_length=255, db_column='user_password')
    user_token = models.CharField('Token', max_length=255, default='', db_column='user_token')
    user_status = models.IntegerField('状态 1-正常 0-停用', db_column='user_status')
    user_power = models.IntegerField('权限', db_column='user_power')
    role_id = models.IntegerField('角色ID', null=True, blank=True, db_column='role_id')
    create_time = models.DateTimeField('创建时间', db_column='create_time')
    login_time = models.DateTimeField('登录时间', db_column='login_time')

    class Meta:
        app_label = 'users'  # 明确归属，对应 INSTALLED_APPS 中的 apps.users
        db_table = 'z_user'
        verbose_name = '用户'
        verbose_name_plural = '用户'
        managed = False  # 表已存在，不生成迁移

    @classmethod
    def get_by_username(cls, user_name):
        try:
            return cls.objects.get(user_name=user_name)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_valid_user_by_token(cls, token):
        """根据 token 获取未过期的用户，过期规则见 apps.users.login_token.is_token_expired。"""
        from .login_token import is_token_expired
        if not token:
            return None
        try:
            user = cls.objects.get(user_token=token)
            if user.user_status != 1:
                return None
            if is_token_expired(user.login_time):
                return None
            return user
        except cls.DoesNotExist:
            return None
