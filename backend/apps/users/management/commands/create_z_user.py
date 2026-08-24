from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.users.models import ZUser


class Command(BaseCommand):
    help = '创建 z_user 表用户（用于登录）'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='用户名')
        parser.add_argument('password', type=str, help='密码')
        parser.add_argument('--cn', type=str, default='', help='中文名 user_cn_name，默认同用户名')

    def handle(self, *args, **options):
        username = options['username'].strip()
        password = options['password']
        cn_name = (options.get('cn') or '').strip() or username
        if not username or not password:
            self.stderr.write(self.style.ERROR('用户名和密码不能为空'))
            return
        if ZUser.objects.filter(user_name=username).exists():
            self.stderr.write(self.style.ERROR(f'用户 {username} 已存在'))
            return
        now = timezone.now()
        ZUser.objects.create(
            user_name=username,
            user_cn_name=cn_name,
            user_password=password,
            user_token='',
            user_status=1,
            user_power=0,
            create_time=now,
            login_time=now,
        )
        self.stdout.write(self.style.SUCCESS(f'用户 {username} 创建成功，可用于登录'))
