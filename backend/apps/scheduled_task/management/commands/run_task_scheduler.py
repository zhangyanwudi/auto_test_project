from django.core.management.base import BaseCommand

from apps.scheduled_task.scheduler_runner import run_forever


class Command(BaseCommand):
    help = (
        '独立进程：读取 z_scheduled_task 中 status=1 的任务，'
        '按 cron_expression 调度执行 task_file 脚本（与「立即运行」同一套逻辑）。'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reload-interval',
            type=int,
            default=60,
            help='从数据库重新加载任务配置的间隔（秒），默认 60',
        )

    def handle(self, *args, **options):
        run_forever(reload_interval=options['reload_interval'])
