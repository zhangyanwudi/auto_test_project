from operator import index

from loguru import logger as loguru_logger
import os, time
from base_utils.path_base import get_path, check_dirs,get_file_time,joint_path
from base_utils.time_base import get_before,get_timestamp_ms
log_dir_path=joint_path(get_path(__file__,index=1),'log')
check_dirs(log_dir_path)
bound_loggers = {}  # 全局变量，用于存储日志记录器实例


def delete_old_files(directory, hours=24):
    """
    删除指定目录下超过指定时间（默认24小时）的文件

    :param directory: 需要处理的目录
    :param hours: 超过指定时间（以小时为单位）的文件将被删除，默认是48小时
    """

    cutoff_time=get_before(days=-5,is_tmiestamp=True)


    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            file_mod_time = get_file_time(file_path)
            if file_mod_time < cutoff_time:
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"删除文件 {file_path} 时出错: {e}")


def setting_logger(file_name="", tag=""):
    # 设置是否带标签消息格式
    if tag:
        format_log = "{time:YYYY-MM-DD at HH:mm:ss} | {level} |【{extra[tag]}】{message}"
    else:
        format_log = "{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}"
    if file_name not in bound_loggers:
        # 创建一个新的日志器实例
        bound_logger = loguru_logger.bind(tag=tag)
        # 使用字符串格式化功能来指定日志文件名，其中的日期部分将会被每天自动更新
        if file_name:
            log_file_path = f"{log_dir_path}/{file_name}_{{time:YYYY-MM-DD}}.log"
        else:
            log_file_path = f"{log_dir_path}/{{time:YYYY-MM-DD}}.log"

        bound_logger.add(
            log_file_path,
            rotation="1 GB",  # 日志文件达到1GB时轮转
            retention="1 days",  # 只保留最近10个日志文件
            compression="zip",  # 轮转后的日志文件压缩为 ZIP 格式
            format=format_log  # 日志格式
        )
        # 将新创建的 logger 存储到字典中
        bound_loggers[file_name] = bound_logger
    return bound_loggers[file_name]


delete_old_files(log_dir_path)