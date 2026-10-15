"""
日志模块 — 基于 loguru 的轻量封装。

使用方式:
    # 开箱即用 — 直接导入 logger 即可
    from base_utils.logger_base import logger
    logger.info("开始处理任务")

    # 按模块分文件记录日志
    from base_utils.logger_base import get_logger
    task_logger = get_logger("sync_task", tag="数据同步")
    task_logger.info("同步完成")
"""

import os
from loguru import logger as loguru_logger
from base_utils.path_base import get_path, check_dirs, get_file_time, joint_path
from base_utils.time_base import get_before

# ---------- 日志目录 ----------
_log_dir = joint_path(get_path(__file__, index=1), 'log')
check_dirs(_log_dir)

# ---------- 日志格式 ----------
_FMT_DEFAULT = "{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}"
_FMT_TAG     = "{time:YYYY-MM-DD at HH:mm:ss} | {level} |【{extra[tag]}】{message}"

# ---------- logger 缓存 & 自动清理标记 ----------
_logger_cache = {}
_auto_cleaned = False


def clean_old_logs(directory=None, days=5):
    """
    清理超过指定天数的旧日志文件。

    :param directory: 日志目录，默认为当前日志目录
    :param days: 删除超过此天数的文件，默认 5 天
    """
    target_dir = directory or _log_dir
    if not os.path.exists(target_dir):
        return

    cutoff_time = get_before(days=-days, is_tmiestamp=True)

    for filename in os.listdir(target_dir):
        file_path = os.path.join(target_dir, filename)
        if not os.path.isfile(file_path):
            continue
        if get_file_time(file_path) < cutoff_time:
            try:
                os.remove(file_path)
            except OSError as e:
                print(f"删除文件 {file_path} 时出错: {e}")


def get_logger(file_name="", tag=""):
    """
    获取或创建一个 logger 实例（同名同 tag 会复用已有实例）。
    首次调用时会自动清理过期日志。

    :param file_name: 日志文件名前缀，如 "task" → task_2026-07-29.log
    :param tag: 可选标签，会显示在日志的【】中
    :return: loguru logger 实例
    """
    # 首次使用时自动清理旧日志，整个进程生命周期只执行一次
    global _auto_cleaned
    if not _auto_cleaned:
        _auto_cleaned = True
        try:
            clean_old_logs()
        except Exception:
            pass  # 清理失败不影响正常日志记录

    cache_key = f"{file_name}|{tag}"

    if cache_key not in _logger_cache:
        log_format = _FMT_TAG if tag else _FMT_DEFAULT

        # 构建日志文件路径（{time} 由 loguru 自动填充为日期）
        prefix = f"{file_name}_" if file_name else ""
        log_file_path = f"{_log_dir}/{prefix}{{time:YYYY-MM-DD}}.log"

        # 创建绑定 logger 并添加文件 sink
        # 注意：loguru 的所有 Logger 共享同一个底层 core，.add() 注册的 handler 是全局的，
        # 所以必须给每条记录打上隐藏标识 _log_file，再用 filter 按 file_name 精确隔离，
        # 否则不同模块的日志会互相串文件。同时：
        #   - 带 tag 的 format 引用了 {extra[tag]}，无 tag 的记录若流经该 handler 会触发
        #     KeyError: 'tag'，因此 tag 与无 tag 的 handler 也要分开过滤；
        #   - 多个 tag 共用同一 file_name（如 gp_block_log）时，按 tag 精确匹配，避免同一行写两次。
        bind_kwargs = {"_log_file": file_name}
        if tag:
            bind_kwargs["tag"] = tag
        logger_instance = loguru_logger.bind(**bind_kwargs)

        if tag:
            handler_filter = lambda record: (
                record["extra"].get("_log_file") == file_name
                and record["extra"].get("tag") == tag
            )
        else:
            # 默认 logger（file_name 为空）同时兼容没有 _log_file 标识的记录，作为兜底
            handler_filter = lambda record: (
                record["extra"].get("_log_file", "") == file_name
                and "tag" not in record["extra"]
            )

        logger_instance.add(
            log_file_path,
            rotation="1 GB",
            retention="1 days",
            compression="zip",
            format=log_format,
            filter=handler_filter,
        )

        _logger_cache[cache_key] = logger_instance

    return _logger_cache[cache_key]


# ---------- 模块级默认 logger（import 即用）----------
logger = get_logger()


# ---------- 兼容旧接口 ----------
setting_logger = get_logger
delete_old_files = clean_old_logs
