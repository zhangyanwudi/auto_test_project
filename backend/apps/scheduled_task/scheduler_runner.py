"""
独立调度进程：从 z_scheduled_task 读取启用任务，按 Cron 调用 executor.execute_task_once。
"""
import logging
import signal
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.db import close_old_connections

from apps.scheduled_task.executor import execute_task_once, persist_task_run_result, validate_cron
from apps.scheduled_task.models import ZScheduledTask

logger = logging.getLogger(__name__)

RELOAD_JOB_ID = '_sync_scheduled_tasks'


def run_scheduled_task(task_id: int):
    """Cron 触发时执行单条任务并更新 last_run_time。"""
    close_old_connections()
    try:
        t = ZScheduledTask.objects.get(pk=task_id)
    except ZScheduledTask.DoesNotExist:
        logger.warning('调度跳过：任务 id=%s 已不存在', task_id)
        return
    if t.status != 1:
        logger.info('调度跳过：任务 id=%s code=%s 已停用', task_id, t.task_code)
        return
    logger.info(
        'Cron 触发执行：id=%s code=%s file=%s cron=%s',
        t.id,
        t.task_code,
        t.task_file_name,
        t.cron_expression,
    )
    ok, msg, detail = execute_task_once(t)
    persist_task_run_result(t, ok, msg, detail)
    if ok:
        logger.info('Cron 执行成功：id=%s code=%s %s', t.id, t.task_code, msg)
    else:
        logger.error('Cron 执行失败：id=%s code=%s %s', t.id, t.task_code, msg)


def sync_jobs(scheduler: BackgroundScheduler):
    """从数据库同步 APScheduler 任务（启用项注册，停用/删除项移除）。"""
    close_old_connections()
    enabled = list(ZScheduledTask.objects.filter(status=1).order_by('id'))
    enabled_ids = {t.id for t in enabled}

    for job in scheduler.get_jobs():
        jid = job.id
        if jid == RELOAD_JOB_ID:
            continue
        if jid.startswith('task_'):
            try:
                tid = int(jid[5:], 10)
            except ValueError:
                scheduler.remove_job(jid)
                continue
            if tid not in enabled_ids:
                scheduler.remove_job(jid)
                logger.info('已移除调度：任务 id=%s（停用或已删）', tid)

    tz = settings.TIME_ZONE
    for t in enabled:
        cron = (t.cron_expression or '').strip()
        job_id = f'task_{t.id}'
        if not cron:
            logger.warning('任务 id=%s code=%s 未配置 cron，跳过', t.id, t.task_code)
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            continue
        if validate_cron(cron):
            logger.warning('任务 id=%s code=%s cron 格式无效：%r', t.id, t.task_code, cron)
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            continue
        try:
            trigger = CronTrigger.from_crontab(cron, timezone=tz)
        except Exception as e:
            logger.warning(
                '任务 id=%s code=%s cron 无法解析 %r：%s',
                t.id,
                t.task_code,
                cron,
                e,
            )
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            continue
        scheduler.add_job(
            run_scheduled_task,
            trigger=trigger,
            id=job_id,
            args=[t.id],
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=300,
            coalesce=True,
        )
        logger.info(
            '已注册调度：id=%s code=%s cron=%s file=%s',
            t.id,
            t.task_code,
            cron,
            t.task_file_name or '-',
        )


def run_forever(reload_interval: int = 60):
    """
    阻塞运行调度器。需单独进程：python manage.py run_task_scheduler
    """
    if reload_interval < 10:
        reload_interval = 10

    scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
    sync_jobs(scheduler)
    scheduler.add_job(
        sync_jobs,
        'interval',
        seconds=reload_interval,
        args=[scheduler],
        id=RELOAD_JOB_ID,
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        '定时任务调度器已启动（时区 %s，每 %s 秒从库表重载）',
        settings.TIME_ZONE,
        reload_interval,
    )

    def _shutdown(signum, frame):
        logger.info('收到信号 %s，正在停止调度器…', signum)
        scheduler.shutdown(wait=False)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
        logger.info('定时任务调度器已停止')
