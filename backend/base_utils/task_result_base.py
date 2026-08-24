"""
定时任务脚本执行结果约定。

任务脚本须在 stdout **最后一行**输出 JSON（也可使用 emit_task_result 辅助函数）：
  {"success": true}
  {"success": false, "message": "失败原因"}

success 为 false 时 message 必填。
"""
import json
import sys

TASK_RESULT_FORMAT_HINT = (
    '任务须在 stdout 最后一行输出 JSON：'
    '{"success": true} 或 {"success": false, "message": "失败原因"}'
)


def emit_task_result(success: bool, message: str = "") -> None:
    """
    输出标准任务结果 JSON 并正常退出（供 executor 解析）。
    """
    msg = (message or "").strip()
    if not success and not msg:
        msg = "任务执行失败"
    payload = {"success": bool(success)}
    if msg:
        payload["message"] = msg
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)
