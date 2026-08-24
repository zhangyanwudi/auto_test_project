from base_utils.task_result_base import emit_task_result
from base_utils.time_base import get_date


def run_test_task():
    print(f"任务执行，当前执行时间：{get_date()}")
    emit_task_result(True, "测试任务执行成功")


if __name__ == "__main__":
    run_test_task()
