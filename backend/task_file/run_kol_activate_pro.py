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
import io,json
from contextlib import redirect_stdout

from apis.server_api.kol_api import KolsysApi,KolEnum
from base_utils.task_result_base import TaskResultBuilder
from base_utils.logger_base import logger



# 巡检账号（管理员）；is_debug=True 走测试环境，False 走正式环境
KOL_USER_EMAIL = "zhangyan02195@hungrystudio.com"
IS_DEBUG = False  # 默认正式环境；手动调试请用命令行 `python ... --debug` 切测试环境，不要改这一行！


def _env_label():
    """环境标识（延迟到运行时计算，入口处改了 IS_DEBUG 后仍能正确反映）。"""
    return "测试环境" if IS_DEBUG else "正式环境"


def _check_list_has_data(status, data):
    """检查「返回列表且有数据」：status 为真且 data 为非空列表。"""
    if status is not True:
        return False, f"接口调用失败：{data}"
    if not isinstance(data, list):
        return False, f"返回数据类型异常：{type(data).__name__}"
    if not data:
        return False, "接口成功但未返回数据（空列表）"
    return True, f"返回数据 {len(data)} 条"

def _check_list_has_data_by_none(status, data):
    """检查「返回列表且有数据」：status 为真且 data 为非空列表。"""
    if status is not True:
        return False, f"接口调用失败：{data}"
    if not isinstance(data, list):
        return False, f"返回数据类型异常：{type(data).__name__}"
    if not data:
        return True, "接口成功但未返回数据（空列表）"
    return True, f"返回数据 {len(data)} 条"


# ── 巡检项列表 ──────────────────────────────────────────────
# check 返回 (是否通过, 说明)；func 返回 (status, data)
CASES = [
    {
        "name": "获取达人列表",
        "func": lambda api: api.query_kolsys_daren_list_data(count=10),
        "check": _check_list_has_data,
    },
    {
        "name": "获取订单管理列表",
        "func": lambda api: api.query_kolsys_order_list_data(count=10),
        "check": _check_list_has_data,
    },
    {
        "name": "获取合同管理列表",
        "func": lambda api: api.query_kolsys_contract_list_data(count=10),
        "check": _check_list_has_data,
    },
    {
        "name": "获取履约管理列表",
        "func": lambda api: api.query_kolsys_performances_list_data(count=10),
        "check": _check_list_has_data,
    },
    {
        "name": "获取视频管理列表",
        "func": lambda api: api.query_kolsys_video_list_data(count=10),
        "check": _check_list_has_data,
    },
    {
        "name": "获取结算明细管理列表",
        "func": lambda api: api.query_kolsys_settle_detail_list_data(count=10),
        "check": _check_list_has_data,
    },
    {
        "name": "获取收款单位管理列表",
        "func": lambda api: api.query_kolsys_payees_list_data(count=10),
        "check": _check_list_has_data,
    },
    {
        "name": "获取活动管理列表",
        "func": lambda api: api.query_kolsys_activities_list_data(count=10),
        "check": _check_list_has_data,
    },
    {
        "name": "获取创意管理列表",
        "func": lambda api: api.query_kolsys_creatives_list_data(count=10),
        "check": _check_list_has_data,
    },
    {
        "name": "获取hashtag-单关键词列表",
        "func": lambda api: api.query_kilsys_hashtag_list_data(count=10,keyword_type=KolEnum.KeyWordType.SINGLE.value),
        "check": _check_list_has_data,
    },
    {
        "name": "获取hashtag-多关键词列表",
        "func": lambda api: api.query_kilsys_hashtag_list_data(count=10,keyword_type=KolEnum.KeyWordType.COMPOUND.value),
        "check": _check_list_has_data,
    },
    {
        "name": "获取初次建联达人邮箱列表",
        "func": lambda api: api.query_kolline_daren_email_list_data(count=10),
        "check": _check_list_has_data_by_none,
    },
    {
        "name": "获取follow_up邮箱列表",
        "func": lambda api: api.query_kolline_follow_up_email_list_data(count=10),
        "check": _check_list_has_data_by_none,
    },
    {
        "name": "建联邮件发送记录",
        "func": lambda api: api.query_email_send_record(count=10),
        "check": _check_list_has_data_by_none,
    },
    {
        "name": "获取数据分析列表数据-达人库圈选",
        "func": lambda api: api.query_data_analysis_by_daren_select(task_source=KolEnum.TaskSource.Selected.value,count=10),
        "check": _check_list_has_data_by_none,
    },
    {
        "name": "获取数据分析列表数据-邮件直发",
        "func": lambda api: api.query_data_analysis_by_daren_select(task_source=KolEnum.TaskSource.Direct.value,count=10),
        "check": _check_list_has_data_by_none,
    },
]


def _build_robot_message(case_lines, passed, failed, total):
    """组装机器人消息文本：环境 + 每个接口一行 + 巡检汇总（精简版）。"""
    lines = [f"【达人基建平台--接口巡检】{_env_label()}"]
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
    if not IS_DEBUG:
        from base_utils.robot_message import RobotMessage
        robot = RobotMessage(
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=2f8f18df9b0c5dc33c6a7545edfcddd10490593787b38c53b1176ba1d98bf913",
            secret="SECcfd1ac57db382eb6a3f55f7c0f9aa413e027c0d45042b8ffd713d6238e439354",
        )
        robot.send_text_message(message)
    else:
        print("=" * 44)
        print("【机器人消息预览】")
        print(message)
        print("=" * 44)


def run_kol_activate_pro(only_name=None):
    """执行 KOL 接口巡检，输出完整日志 + 机器人消息，并上报整体结果。

    :param only_name: 仅执行 name 与之精确匹配的巡检项；为 None 时执行全部。
    """
    api = KolsysApi(is_debug=IS_DEBUG)
    result = TaskResultBuilder()

    # 按 --only 过滤巡检项（精确匹配 name）
    if only_name:
        selected = [c for c in CASES if c["name"] == only_name]
        if not selected:
            print(f"[调试] 未找到与 --only 匹配的巡检项：{only_name}")
            print(f"[调试] 可选 name：{', '.join(c['name'] for c in CASES)}")
            return
        cases = selected
        print(f"[调试] --only 命中 {len(cases)} 个巡检项：{only_name}")
    else:
        cases = CASES

    # 前置：刷新巡检账号 token（失败不终止，后续接口会用默认 token 尝试）。
    # get_user_token 内部有裸 print 会打印 token 等敏感信息，这里用 redirect_stdout 吞掉。
    with redirect_stdout(io.StringIO()):
        ok, info = api.get_user_token(KOL_USER_EMAIL, is_set_cache=False)
    if not ok:
        result.add_fail(f"刷新 token 失败（将以默认 token 继续）：{info}")
        print(f"[巡检] 刷新 token 失败（将以默认 token 继续）：{info}")
    else:
        result.add_success("刷新 token 成功")
        print("[巡检] 刷新 token 成功")

    passed = 0
    failed = 0
    total = len(cases)
    robot_lines = []  # 机器人消息里每个接口的一行（精简版）

    # ── 完整日志（详细）──
    print("=" * 44)
    for i, case in enumerate(cases, start=1):
        name = case["name"]
        print(f"[{i}/{total}] 接口名称：{name}")
        try:
            status, data = case["func"](api)
            # logger.info(json.dumps(data))
            ok, detail = case["check"](status, data)
        except Exception as e:  # noqa: BLE001 巡检兜底，单个接口异常不影响汇总
            ok, detail = False, f"执行异常：{e}"
        # 运行消息统一收集到 result（最终体现在页面「成功消息/失败消息」），
        # 同时作为机器人消息的精简版一行。
        if ok:
            passed += 1
            line = f"[{i}/{total}] {name}：✅ 通过（{detail}）"
            result.add_success(line)
            robot_lines.append(line)
        else:
            failed += 1
            line = f"[{i}/{total}] {name}：❌ 失败（{detail}）"
            result.add_fail(line)
            robot_lines.append(line)
        print(f"  检查结果：{'✅ 通过' if ok else '❌ 失败'}（{detail}）")
    print("=" * 44)
    print(f"巡检汇总：通过 {passed} / 失败 {failed} / 共 {total}")

    # ── 机器人消息（精简版，不含结果上报 JSON）──
    robot_msg = _build_robot_message(robot_lines, passed, failed, total)
    _send_robot_message(robot_msg)

    # ── 任务结果上报：下方 JSON 供定时任务系统解析（判断成功/失败），
    #    不是机器人消息，不会通过机器人发送 ──
    print("[任务结果上报] 下方 JSON 供调度系统解析，非机器人消息：")
    if failed:
        result.emit(False, f"KOL 接口巡检：通过 {passed} / 失败 {failed} / 共 {total}")
    else:
        result.emit(True, f"KOL 接口巡检通过 {passed}/{total}")


if __name__ == "__main__":
    import sys

    # 命令行参数决定运行环境（executor 调度执行时无参数，不会命中，保持默认正式）
    if "--debug" in sys.argv:
        IS_DEBUG = True
        print("[运行模式] 测试环境(debug)：真实调用测试接口，机器人仅预览、不真实发送")
    elif "--prod" in sys.argv:
        IS_DEBUG = False
        print("[运行模式] ⚠️ 正式环境(prod)：真实调用正式接口并发送机器人")

    # --only 后的内容与 CASES 中 name 精确匹配才执行；取第一个 --only 参数
    only_name = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only_name = sys.argv[idx + 1]

    run_kol_activate_pro(only_name=only_name)
