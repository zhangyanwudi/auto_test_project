# -*- coding: utf-8 -*-
"""
KOL 接口巡检任务（run_kol_activate_pro）

对 kol_api 中的部分接口进行巡检：
  1. 先调用 get_user_token 刷新巡检账号 token（前置准备，失败不终止，会以默认 token 继续）
  2. 逐个执行 CASES 里配置的接口巡检项
  3. 每个接口输出「接口名称 + 检查结果（通过 ✅ / 失败 ❌）」
  4. 最后通过 emit_task_result 上报整体结果（全部通过才 success=true）

输出分两套：
  - 完整日志：stdout 详细输出（供 executor 捕获与排查）
  - 机器人消息：精简版（环境 + 每个接口一行 + 巡检汇总），
    当前先用 print 输出预览，确认格式后改为 _send_robot_message 实际发送

新增巡检项：往 CASES 列表追加一条 {name, func, check} 即可。
  - name:  接口名称（展示用）
  - func:  调用函数，接收 api 实例，返回 (status, data)
  - check: 检查函数，接收 (status, data)，返回 (是否通过, 说明)

运行方式（由 scheduled_task executor 自动执行，也可本地验证）：
  PYTHONPATH=<backend> python -u task_file/run_kol_activate_pro.py
"""
import io
from contextlib import redirect_stdout

from apis.server_api.kol_api import KolsysApi
from base_utils.task_result_base import emit_task_result

# 巡检账号（管理员）；is_debug=True 走测试环境，False 走正式环境
KOL_USER_EMAIL = "zhangyan02195@hungrystudio.com"
IS_DEBUG = True

# 环境标识（最上面展示给机器人/日志）
ENV_LABEL = "测试环境" if IS_DEBUG else "正式环境"


def _check_list_has_data(status, data):
    """检查「返回列表且有数据」：status 为真且 data 为非空列表。"""
    if status is not True:
        return False, f"接口调用失败：{data}"
    if not isinstance(data, list):
        return False, f"返回数据类型异常：{type(data).__name__}"
    if not data:
        return False, "接口成功但未返回数据（空列表）"
    return True, f"返回数据 {len(data)} 条"


# ── 巡检项列表 ──────────────────────────────────────────────
# check 返回 (是否通过, 说明)；func 返回 (status, data)
CASES = [
    {
        "name": "query_kol_users（获取达人列表）",
        "func": lambda api: api.query_kol_users(count=10),
        "check": _check_list_has_data,
    },
]


def _build_robot_message(case_lines, passed, failed, total):
    """组装机器人消息文本：环境 + 每个接口一行 + 巡检汇总（精简版）。"""
    lines = [f"【KOL接口巡检】{ENV_LABEL}"]
    lines.extend(case_lines)
    lines.append(f"巡检汇总：通过 {passed} / 失败 {failed} / 共 {total}")
    return "\n".join(lines)


def _send_robot_message(message):
    """发送机器人消息。

    TODO：确认格式后，替换为真实钉钉机器人发送，例如：
        from base_utils.config_base import get_config
        from base_utils.robot_message import RobotMessage
        robot = RobotMessage(
            get_config('dingtalk', 'robot_webhook_url', ''),
            secret=get_config('dingtalk', 'robot_secret', ''),
        )
        robot.send_text_message(message)
    当前先用 print 输出预览，便于确认格式。
    """
    print("=" * 44)
    print("【机器人消息预览】")
    print(message)
    print("=" * 44)


def run_kol_activate_pro():
    """执行 KOL 接口巡检，输出完整日志 + 机器人消息，并上报整体结果。"""
    api = KolsysApi(is_debug=IS_DEBUG)

    # 前置：刷新巡检账号 token（失败不终止，后续接口会用默认 token 尝试）。
    # get_user_token 内部有裸 print 会打印 token 等敏感信息，这里用 redirect_stdout 吞掉。
    with redirect_stdout(io.StringIO()):
        ok, info = api.get_user_token(KOL_USER_EMAIL, is_set_cache=False)
    if not ok:
        print(f"[巡检] 刷新 token 失败（将以默认 token 继续）：{info}")
    else:
        print("[巡检] 刷新 token 成功")

    passed = 0
    failed = 0
    total = len(CASES)
    fail_msgs = []
    robot_lines = []  # 机器人消息里每个接口的一行（精简版）

    # ── 完整日志（详细）──
    print("=" * 44)
    for i, case in enumerate(CASES, start=1):
        name = case["name"]
        print(f"[{i}/{total}] 接口名称：{name}")
        try:
            status, data = case["func"](api)
            ok, detail = case["check"](status, data)
        except Exception as e:  # noqa: BLE001 巡检兜底，单个接口异常不影响汇总
            ok, detail = False, f"执行异常：{e}"
        if ok:
            passed += 1
            print(f"  检查结果：✅ 通过（{detail}）")
            robot_lines.append(f"[{i}/{total}] 接口名称：{name}  检查结果：✅ 通过（{detail}）")
        else:
            failed += 1
            fail_msgs.append(f"{name}：{detail}")
            print(f"  检查结果：❌ 失败（{detail}）")
            robot_lines.append(f"[{i}/{total}] 接口名称：{name}  检查结果：❌ 失败（{detail}）")
    print("=" * 44)
    print(f"巡检汇总：通过 {passed} / 失败 {failed} / 共 {total}")

    # ── 机器人消息（精简版，不含结果上报 JSON）──
    robot_msg = _build_robot_message(robot_lines, passed, failed, total)
    _send_robot_message(robot_msg)

    # ── 任务结果上报：下方 JSON 供定时任务系统解析（判断成功/失败），
    #    不是机器人消息，不会通过机器人发送 ──
    print("[任务结果上报] 下方 JSON 供调度系统解析，非机器人消息：")
    if failed:
        emit_task_result(False, "；".join(fail_msgs))
    else:
        emit_task_result(True, f"KOL 接口巡检通过 {passed}/{total}")


if __name__ == "__main__":
    run_kol_activate_pro()
