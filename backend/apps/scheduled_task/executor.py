"""
定时任务脚本执行：供 API「立即运行」与独立调度进程共用。
"""
import json
import logging
import os
import platform
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.scheduled_task.models import ZScheduledTask, ZScheduledTaskRunLog
from base_utils.task_result_base import TASK_RESULT_FORMAT_HINT
from base_utils.time_base import format_datetime_utc8

logger = logging.getLogger(__name__)

_MAX_CAPTURE = 8000
_MAX_DETAIL_JSON = 8000


def build_run_result(ok: bool, message: str, detail=None) -> dict:
    """统一执行结果结构，供 API 与前端展示。"""
    return {
        'success': bool(ok),
        'message': message or ('执行成功' if ok else '执行失败'),
        'detail': detail if isinstance(detail, dict) else {},
    }


def _json_default(obj):
    """json.dumps 的 default 处理：datetime 统一转 UTC+8 字符串，避免序列化失败。"""
    if isinstance(obj, datetime):
        return format_datetime_utc8(obj)
    return str(obj)


def _detail_to_json(detail) -> str:
    if not detail:
        return ''
    try:
        s = json.dumps(detail, ensure_ascii=False, default=_json_default)
    except (TypeError, ValueError):
        return ''
    if len(s) > _MAX_DETAIL_JSON:
        return s[:_MAX_DETAIL_JSON] + '...'
    return s


def persist_task_run_result(task: ZScheduledTask, ok: bool, message: str, detail=None) -> ZScheduledTask:
    """写入最近执行时间、成功标记、说明与详情（定时调度与立即运行共用）。"""
    task.last_run_time = timezone.now()
    task.last_run_success = bool(ok)
    task.last_run_message = (message or '')[:512]
    task.last_run_detail = _detail_to_json(detail)
    task.save(
        update_fields=[
            'last_run_time',
            'last_run_success',
            'last_run_message',
            'last_run_detail',
        ]
    )
    return task


def persist_task_run_log(task_id, trigger_type, ok, message, detail=None, start_time=None, end_time=None):
    """写入一条执行日志记录（立即运行与定时调度共用）。"""
    start = start_time or timezone.now()
    end = end_time or timezone.now()
    duration_ms = int((end - start).total_seconds() * 1000)
    if duration_ms < 0:
        duration_ms = 0
    return ZScheduledTaskRunLog.objects.create(
        task_id=int(task_id),
        trigger_type=trigger_type or ZScheduledTaskRunLog.TRIGGER_MANUAL,
        start_time=start,
        end_time=end,
        duration_ms=duration_ms,
        success=bool(ok),
        message=(message or '')[:512],
        detail_json=_detail_to_json(detail),
    )


def try_mark_task_running(task_id):
    """尝试把任务标记为「运行中」（CAS：仅当空闲时置 1）。

    返回 True 表示抢占成功、可执行；False 表示已在运行中，应跳过本次执行。
    """
    updated = ZScheduledTask.objects.filter(pk=task_id, is_running=False).update(is_running=True)
    return updated == 1


def finalize_task_run(task: ZScheduledTask, ok: bool, message: str, detail=None, trigger_type=None):
    """任务执行收尾：落结果、写日志、清除运行中标记（立即运行与定时调度共用）。"""
    try:
        persist_task_run_result(task, ok, message, detail)
    finally:
        persist_task_run_log(
            task_id=task.id,
            trigger_type=trigger_type or ZScheduledTaskRunLog.TRIGGER_MANUAL,
            ok=ok,
            message=message,
            detail=detail,
            start_time=(detail or {}).get('start_time'),
        )
        ZScheduledTask.objects.filter(pk=task.id).update(is_running=False)


def parse_stored_run_detail(raw: str):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

# 标准 5 段 crontab：分 时 日 月 周
CRON_5 = re.compile(r'^\S+\s+\S+\s+\S+\s+\S+\s+\S+$')

_TASK_RESULT_PREFIX = '@TASK_RESULT@'


def _coerce_msg_list(raw):
    """把 success_msgs / fail_msgs 规整为字符串列表（过滤空值、截断单条长度）。"""
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s[:_MAX_CAPTURE]] if s else []
    if isinstance(raw, (list, tuple)):
        out = []
        for item in raw:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s[:_MAX_CAPTURE])
        return out
    s = str(raw).strip()
    return [s[:_MAX_CAPTURE]] if s else []


def _coerce_success_value(raw):
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ('true', '1', 'yes', 'on'):
            return True
        if s in ('false', '0', 'no', 'off'):
            return False
    return None


def _try_parse_result_line(line: str):
    s = (line or '').strip()
    if not s:
        return None
    if s.startswith(_TASK_RESULT_PREFIX):
        s = s[len(_TASK_RESULT_PREFIX) :].strip()
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    ok_raw = obj.get('success')
    if ok_raw is None:
        ok_raw = obj.get('result')
    ok = _coerce_success_value(ok_raw)
    if ok is None:
        return None
    msg = (
        obj.get('message')
        or obj.get('reason')
        or obj.get('msg')
        or obj.get('error')
        or ''
    )
    msg = str(msg).strip()
    if not ok and not msg:
        msg = '任务返回失败但未提供 message 失败原因'
    elif ok and not msg:
        msg = '执行成功'

    success_msgs = _coerce_msg_list(obj.get('success_msgs'))
    fail_msgs = _coerce_msg_list(obj.get('fail_msgs'))
    # 兜底：未显式提供 message 时，用失败/成功消息拼接，便于列表直接展示结果。
    if not msg:
        if fail_msgs:
            msg = '；'.join(fail_msgs)
        elif success_msgs:
            msg = '；'.join(success_msgs)

    return {
        'success': ok,
        'message': msg,
        'success_msgs': success_msgs,
        'fail_msgs': fail_msgs,
    }


def parse_task_script_result(stdout: str):
    """
    从任务 stdout 解析 {"success": bool, "message"?: str}。
    优先取最后一行；若无合法 JSON，自后向前扫描。
    返回 (result_dict | None, error_message | None)
    """
    text = (stdout or '').strip()
    if not text:
        return None, f'任务未输出执行结果。{TASK_RESULT_FORMAT_HINT}'
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in reversed(lines):
        parsed = _try_parse_result_line(line)
        if parsed is not None:
            return parsed, None
    return None, f'任务未返回合法执行结果。{TASK_RESULT_FORMAT_HINT}'


def task_file_dir() -> Path:
    """backend/task_file：存放可被选为定时任务执行的文件。"""
    d = (Path(settings.BASE_DIR) / 'task_file').resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_task_file_names():
    root = task_file_dir()
    names = []
    for p in sorted(root.iterdir()):
        if p.is_file() and p.name != '.gitkeep':
            names.append(p.name)
    return names


def normalize_task_file_basename(name: str) -> str:
    s = (name or '').strip()
    if not s:
        return ''
    s = s.replace('\\', '/').strip('/')
    for prefix in ('backend/task_file/', 'task_file/'):
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix) :].lstrip('/')
            break
    base = Path(s).name
    if not base or base in ('.', '..'):
        return ''
    if '/' in s or '\\' in s:
        return base
    return base


def task_file_allowed(name: str) -> bool:
    base = normalize_task_file_basename(name)
    if not base or base in ('.', '..'):
        return False
    root = task_file_dir().resolve()
    p = (root / base).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return False
    return p.is_file()


def validate_cron(expr: str):
    s = (expr or '').strip()
    if not s or not CRON_5.match(s):
        return 'Cron 须为 5 段，以空格分隔，例如：30 9 * * *（每天 9:30）或 */5 * * * *（每 5 分钟）'
    return None


def _truncate_out(s: str, limit: int = _MAX_CAPTURE) -> str:
    if not s:
        return ''
    s = str(s)
    if len(s) <= limit:
        return s
    return s[:limit] + '\n... (输出已截断)'


def _log_captured_subprocess_io(stdout, stderr, log_max=4000):
    out = (stdout or '').strip()
    if out:
        s = out if len(out) <= log_max else out[:log_max] + '\n... (日志已截断)'
        logger.info('scheduled_task 子进程 stdout:\n%s', s)
    err = (stderr or '').strip()
    if err:
        s = err if len(err) <= log_max else err[:log_max] + '\n... (日志已截断)'
        logger.warning('scheduled_task 子进程 stderr:\n%s', s)


def _build_run_command(script_path: Path):
    suf = script_path.suffix.lower()
    if suf == '.py':
        return [sys.executable, '-u', str(script_path.resolve())], None
    if suf in ('.sh', '.bash', '.zsh'):
        if platform.system() == 'Windows':
            return None, '当前环境为 Windows，不支持直接运行 Shell 脚本（.sh/.bash/.zsh）'
        return ['/bin/sh', str(script_path)], None
    if platform.system() == 'Windows' and suf in ('.bat', '.cmd'):
        return ['cmd.exe', '/c', str(script_path)], None
    if suf == '':
        if platform.system() == 'Windows':
            return None, 'Windows 下请使用 .py、.bat 或 .cmd 等明确后缀的任务文件'
        return ['/bin/sh', str(script_path)], None
    return None, f'暂不支持的文件类型「{suf or "无后缀"}」，请使用 .py（全平台）或 Windows 下 .bat/.cmd'


def _subprocess_env():
    root = str(Path(settings.BASE_DIR).resolve())
    env = {**os.environ}
    pp = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = f'{root}{os.pathsep}{pp}' if pp else root
    return env


def execute_task_once(task, task_file_name_override=None):
    """
    执行一次任务。返回 (ok: bool, message: str, detail: dict)

    detail 中统一附带 'start_time' / 'end_time' / 'duration_ms'，供写执行日志使用。
    """
    started = timezone.now()
    et = (task.execution_type or 'file').strip() or 'file'
    if et != 'file':
        return False, '当前任务为「其他」类型，无可执行文件', {'start_time': started}
    raw = (task.task_file_name or '').strip()
    if task_file_name_override is not None and str(task_file_name_override).strip() != '':
        raw = str(task_file_name_override).strip()
    name = normalize_task_file_basename(raw)
    task_root = task_file_dir()
    if not name:
        return False, '未配置执行文件名（task_file_name）', {'start_time': started}
    if not task_file_allowed(name):
        expected = (task_root.resolve() / name).resolve()
        hint = (
            f'服务器上未找到或未授权该文件：{raw!r}（解析为 {name!r}）。'
            f'请将文件放到服务端目录：{task_root.resolve()}（期望路径：{expected}）。'
        )
        return False, hint, {'start_time': started, 'expected_path': str(expected)}
    script_path = (task_root / name).resolve()
    cmd, err = _build_run_command(script_path)
    if err:
        return False, err, {'start_time': started, 'command': cmd, 'script_path': str(script_path)}
    cwd = str(Path(settings.BASE_DIR).resolve())
    detail_base = {
        'command': cmd,
        'script_path': str(script_path),
        'cwd': cwd,
    }
    try:
        logger.info('scheduled_task run: cmd=%s cwd=%s', cmd, cwd)
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=600,
            env=_subprocess_env(),
        )
        logger.info('scheduled_task run done: returncode=%s', proc.returncode)
        _log_captured_subprocess_io(proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired:
        return False, '执行超时（超过 600 秒）', {**detail_base, 'start_time': started, 'returncode': None}
    except Exception as e:
        logger.exception('scheduled_task run failed: %s', e)
        return False, f'执行过程异常：{e}', {**detail_base, 'start_time': started}
    detail = {**detail_base, 'start_time': started, 'returncode': proc.returncode}
    parsed, parse_err = parse_task_script_result(proc.stdout)
    if parsed is not None:
        ok = parsed['success']
        msg = parsed['message']
        detail['task_result'] = parsed
        # 有合法结果 JSON 时，用任务回传的成功/失败消息展示，不再兜底输出 stdout/stderr
        detail['success_msgs'] = parsed.get('success_msgs') or []
        detail['fail_msgs'] = parsed.get('fail_msgs') or []
        return ok, msg, detail
    # 未解析到合法结果 JSON：保留 stdout/stderr 供排查
    detail['stdout'] = _truncate_out(proc.stdout or '')
    detail['stderr'] = _truncate_out(proc.stderr or '')
    if proc.returncode != 0:
        return False, f'脚本退出码 {proc.returncode}，且未返回任务结果 JSON', detail
    return False, parse_err or TASK_RESULT_FORMAT_HINT, detail
