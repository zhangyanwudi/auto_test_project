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
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.scheduled_task.models import ZScheduledTask
from base_utils.task_result_base import TASK_RESULT_FORMAT_HINT

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


def _detail_to_json(detail) -> str:
    if not detail:
        return ''
    try:
        s = json.dumps(detail, ensure_ascii=False)
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
    return {'success': ok, 'message': msg}


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
    """
    et = (task.execution_type or 'file').strip() or 'file'
    if et != 'file':
        return False, '当前任务为「其他」类型，无可执行文件', {}
    raw = (task.task_file_name or '').strip()
    if task_file_name_override is not None and str(task_file_name_override).strip() != '':
        raw = str(task_file_name_override).strip()
    name = normalize_task_file_basename(raw)
    task_root = task_file_dir()
    if not name:
        return False, '未配置执行文件名（task_file_name）', {}
    if not task_file_allowed(name):
        expected = (task_root.resolve() / name).resolve()
        hint = (
            f'服务器上未找到或未授权该文件：{raw!r}（解析为 {name!r}）。'
            f'请将文件放到服务端目录：{task_root.resolve()}（期望路径：{expected}）。'
        )
        return False, hint, {'expected_path': str(expected)}
    script_path = (task_root / name).resolve()
    cmd, err = _build_run_command(script_path)
    if err:
        return False, err, {'command': cmd, 'script_path': str(script_path)}
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
        return False, '执行超时（超过 600 秒）', {**detail_base, 'returncode': None}
    except Exception as e:
        logger.exception('scheduled_task run failed: %s', e)
        return False, f'执行过程异常：{e}', detail_base
    detail = {
        **detail_base,
        'returncode': proc.returncode,
        'stdout': _truncate_out(proc.stdout or ''),
        'stderr': _truncate_out(proc.stderr or ''),
    }
    parsed, parse_err = parse_task_script_result(proc.stdout)
    if parsed is not None:
        ok = parsed['success']
        msg = parsed['message']
        detail['task_result'] = parsed
        return ok, msg, detail
    if proc.returncode != 0:
        return False, f'脚本退出码 {proc.returncode}，且未返回任务结果 JSON', detail
    return False, parse_err or TASK_RESULT_FORMAT_HINT, detail
