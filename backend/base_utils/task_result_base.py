"""
定时任务脚本执行结果约定。

任务脚本须在 stdout **最后一行**输出 JSON（也可使用 emit_task_result 辅助函数）：
  {"success": true}
  {"success": false, "message": "失败原因"}

success 为 false 时 message 必填。

除 message 外，任务还可通过 success_msgs / fail_msgs 字段向页面回传
「成功消息」「失败消息」列表（例如巡检任务里逐条收集的检查结果），
页面据此展示；无记录时前端不展示。

推荐用法：
  from base_utils.task_result_base import TaskResultBuilder
  result = TaskResultBuilder()
  result.add_success("query_kol_users 通过")
  result.add_fail("query_kol_users 失败：返回数据为空")
  result.emit()  # 或 result.emit(False, "汇总失败说明")
"""
import json
import sys

TASK_RESULT_FORMAT_HINT = (
    '任务须在 stdout 最后一行输出 JSON：'
    '{"success": true} 或 {"success": false, "message": "失败原因"}'
)


def _as_message_list(value):
    """把 value 规整为字符串列表（过滤空值）。"""
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []


def _build_payload(success: bool, message: str = "", success_msgs=None, fail_msgs=None) -> dict:
    """组装任务结果 JSON payload（供 emit_task_result 与 TaskResultBuilder 共用）。"""
    msg = (message or "").strip()
    if not success and not msg:
        msg = "任务执行失败"
    payload = {"success": bool(success)}
    if msg:
        payload["message"] = msg
    success_msgs = _as_message_list(success_msgs)
    if success_msgs:
        payload["success_msgs"] = success_msgs
    fail_msgs = _as_message_list(fail_msgs)
    if fail_msgs:
        payload["fail_msgs"] = fail_msgs
    return payload


def emit_task_result(success: bool, message: str = "", success_msgs=None, fail_msgs=None) -> None:
    """
    输出标准任务结果 JSON 并正常退出（供 executor 解析）。
    """
    print(
        json.dumps(
            _build_payload(success, message, success_msgs, fail_msgs),
            ensure_ascii=False,
        )
    )
    sys.exit(0)


class TaskResultBuilder:
    """收集任务运行过程中的成功/失败消息，最后一次性上报。

    用法：
        result = TaskResultBuilder()
        result.add_success("A 接口通过")
        result.add_fail("B 接口失败：xxx")
        result.emit(success=True, message="全部通过")
    """

    def __init__(self):
        self._success_msgs = []
        self._fail_msgs = []

    def add_success(self, message: str) -> None:
        """追加一条成功消息。"""
        s = (message or "").strip()
        if s:
            self._success_msgs.append(s)

    def add_fail(self, message: str) -> None:
        """追加一条失败消息。"""
        s = (message or "").strip()
        if s:
            self._fail_msgs.append(s)

    def emit(self, success: bool = True, message: str = "") -> None:
        """按收集到的消息输出结果 JSON 并退出（executor 解析）。"""
        emit_task_result(success, message, self._success_msgs, self._fail_msgs)
