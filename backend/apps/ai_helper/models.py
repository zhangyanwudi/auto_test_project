from django.db import models
from apps.users.models import ZUser


class AiConversation(models.Model):
    """AI 对话会话"""
    conversation_code = models.CharField(
        '对话编码', max_length=64, unique=True, db_index=True,
        help_text='对外暴露的唯一标识',
    )
    user = models.ForeignKey(
        ZUser, on_delete=models.CASCADE, db_column='user_id',
        verbose_name='所属用户',
    )
    title = models.CharField('对话标题', max_length=128, blank=True, default='')
    is_deleted = models.BooleanField('软删除', default=False)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        app_label = 'ai_helper'
        db_table = 'ai_conversation'
        verbose_name = 'AI对话'
        verbose_name_plural = 'AI对话'
        ordering = ['-update_time']
        managed = False

    def __str__(self):
        return self.title or f'对话 {self.conversation_code[:8]}'


class AiMessage(models.Model):
    """AI 对话消息"""
    ROLE_CHOICES = (
        ('user', '用户'),
        ('assistant', '助手'),
    )
    conversation = models.ForeignKey(
        AiConversation, on_delete=models.CASCADE, db_column='conversation_id',
        verbose_name='所属对话', related_name='messages',
    )
    role = models.CharField('角色', max_length=16, choices=ROLE_CHOICES)
    content = models.TextField('消息内容')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        app_label = 'ai_helper'
        db_table = 'ai_message'
        verbose_name = 'AI消息'
        verbose_name_plural = 'AI消息'
        ordering = ['id']
        managed = False

    def __str__(self):
        return f'{self.role}: {self.content[:50]}'
