from base_utils.task_result_base import TaskResultBuilder
from base_utils.time_base import get_date


def run_test_task():
    print(f"任务执行，当前执行时间：{get_date()}")
    result = TaskResultBuilder()
    result.add_success("测试任务执行成功")
    result.emit(True, "测试任务执行成功")


if __name__ == "__main__":
    run_test_task()
